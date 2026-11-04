"""
High-level async service patterns for common nng messaging topologies.

Provides ``Rep0Service``, a concurrent request/reply server that manages
multiple nng contexts behind a simple ``async for`` interface.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
import logging
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, TypeVar
import warnings

import sniffio

import pynng

from .exceptions import Closed, Timeout

if TYPE_CHECKING:
    from . import _base


logger = logging.getLogger(__name__)

_RequestSelfT = TypeVar("_RequestSelfT", bound="Request")
_ServiceSelfT = TypeVar("_ServiceSelfT", bound="Rep0Service")


class _EventLike(Protocol):
    def set(self) -> None: ...
    async def wait(self) -> object: ...


class _SendChannelLike(Protocol):
    async def send(self, value: Request) -> None: ...
    async def aclose(self) -> None: ...


class _ReceiveChannelLike(Protocol):
    async def receive(self) -> Request: ...


class _CancelScopeLike(Protocol):
    def cancel(self) -> object: ...


class _NurseryLike(Protocol):
    @property
    def cancel_scope(self) -> _CancelScopeLike: ...

    def start_soon(
        self,
        async_fn: Callable[..., Coroutine[object, None, None]],
        *args: object,
    ) -> None: ...


class _NurseryManagerLike(Protocol):
    async def __aenter__(self) -> _NurseryLike: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
        /,
    ) -> object: ...


class Request:
    """A single incoming request received by a :class:`Rep0Service`.

    Attributes:
        data (bytes): The raw request payload.
        context: The :class:`~pynng.Context` that received this request.
            Users should not interact with the context directly; use
            :meth:`reply` instead.

    """

    __slots__ = (
        "_replied",
        "_replied_event",
        "context",
        "data",
    )

    data: bytes
    context: _base.Context
    _replied: bool
    _replied_event: _EventLike | None

    def __init__(
        self,
        data: bytes,
        context: _base.Context,
        _replied_event: _EventLike | None = None,
    ) -> None:
        self.data = data
        self.context = context
        self._replied = False
        self._replied_event = _replied_event

    async def reply(self, data: _base.ReadableBuffer) -> None:
        """Send a response back to the requester.

        Args:
            data (bytes, bytearray, or memoryview): The response payload.

        Raises:
            RuntimeError: If this request has already been replied to.
        """
        if self._replied:
            raise RuntimeError("This request has already been replied to")
        self._replied = True
        try:
            await self.context.asend(data)
        finally:
            if self._replied_event is not None:
                self._replied_event.set()

    def __enter__(self: _RequestSelfT) -> _RequestSelfT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if not self._replied and self._replied_event is not None:
            self._replied_event.set()

    async def __aenter__(self: _RequestSelfT) -> _RequestSelfT:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if not self._replied and self._replied_event is not None:
            self._replied_event.set()

    def __del__(self) -> None:
        if not self._replied:
            if self._replied_event is not None:
                self._replied_event.set()
            warnings.warn(
                f"Request with data {self.data[:64] if self.data else self.data!r} was never replied to",
                ResourceWarning,
                stacklevel=1,
            )


class Rep0Service(AsyncIterator[Request]):
    """High-level async REP service that handles concurrent requests.

    Creates a :class:`~pynng.Rep0` socket (or uses the one passed as
    ``socket``), listens on the given address, and spawns ``workers``
    context-based receive loops.  Incoming requests are placed into an
    internal queue and yielded via ``async for``.

    Works with both asyncio and trio.

    Example::

        async with Rep0Service("tcp://0.0.0.0:5555", workers=4) as service:
            async for request in service:
                await request.reply(process(request.data))

    Args:
        address (str or None): The address to listen on (e.g.
            ``"tcp://0.0.0.0:5555"`` or ``"inproc://my-service"``).  May be
            ``None`` only when ``socket`` is given.
        workers (int): Number of concurrent context workers. Each worker can
            handle one request at a time.  Defaults to 4.
        recv_timeout (int or None): Receive timeout in milliseconds for the
            underlying socket.  ``None`` means no timeout.
        send_timeout (int or None): Send timeout in milliseconds for the
            underlying socket.  ``None`` means no timeout.
        socket: An open, non-raw :class:`~pynng.Rep0` to use instead of
            creating one.  The service does not close it.  When ``address`` is
            also given, the service listens on it with this socket and closes
            that listener on exit.  ``recv_timeout`` and ``send_timeout`` are
            set on the socket while the service runs, and the previous values
            are restored on exit.
    """

    _socket_class: type[_base.Socket] | None = None

    def __init__(
        self,
        address: str | bytes | None = None,
        *,
        workers: int = 4,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        socket: _base.Socket | None = None,
    ) -> None:
        if address is None and socket is None:
            raise ValueError("Either address or socket must be provided")
        if socket is not None:
            expected = self._socket_class or pynng.Rep0
            if not isinstance(socket, expected):
                raise TypeError(
                    f"Expected a {expected.__module__}.{expected.__name__} "
                    f"socket, got {type(socket).__name__}"
                )
            if getattr(socket, "raw", False):
                raise ValueError("A raw Rep0 socket has no contexts")
        self._address = address
        self._workers = workers
        self._recv_timeout = recv_timeout
        self._send_timeout = send_timeout
        self._socket: _base.Socket | None = socket
        self._owns_socket = socket is None
        self._listener: _base.Listener | None = None
        self._saved_timeouts: tuple[int, int] | None = None
        self._contexts: list[_base.Context] = []
        self._queue: asyncio.Queue[Request | object] | None = None
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._running = False
        self._sentinel = object()
        self._trio_send_channel: _SendChannelLike | None = None
        self._trio_recv_channel: _ReceiveChannelLike | None = None
        self._nursery_manager: _NurseryManagerLike | None = None
        self._nursery: _NurseryLike | None = None

    async def __aenter__(self: _ServiceSelfT) -> _ServiceSelfT:
        if self._socket is None:
            sock_cls = self._socket_class or pynng.Rep0
            self._socket = sock_cls(
                listen=self._address,
                recv_timeout=self._recv_timeout,
                send_timeout=self._send_timeout,
            )
            self._owns_socket = True
        else:
            self._saved_timeouts = (
                self._socket.recv_timeout,
                self._socket.send_timeout,
            )
            try:
                if self._recv_timeout is not None:
                    self._socket.recv_timeout = self._recv_timeout
                if self._send_timeout is not None:
                    self._socket.send_timeout = self._send_timeout
                if self._address is not None:
                    self._listener = self._socket.listen(self._address)
            except BaseException:
                self._release_socket()
                raise

        try:
            try:
                backend = sniffio.current_async_library()
            except sniffio.AsyncLibraryNotFoundError:
                backend = "asyncio"

            if backend == "trio":
                await self._start_trio()
            else:
                await self._start_asyncio()
        except BaseException:
            self._release_socket()
            raise

        return self

    def _release_socket(self) -> None:
        """Close an owned socket, or undo what the service did to a borrowed one."""
        if self._socket is None:
            return
        if self._owns_socket:
            self._socket.close()
            self._socket = None
            return
        listener, self._listener = self._listener, None
        saved, self._saved_timeouts = self._saved_timeouts, None
        try:
            if listener is not None:
                listener.close()
            if saved is not None:
                self._socket.recv_timeout, self._socket.send_timeout = saved
        except Closed:
            # The caller closed the socket, which also closed the listener.
            pass

    async def _start_asyncio(self) -> None:
        self._queue = asyncio.Queue()
        self._running = True
        self._contexts = []
        self._worker_tasks = []

        assert self._socket is not None
        for _ in range(self._workers):
            ctx = self._socket.new_context()
            self._contexts.append(ctx)
            task = asyncio.ensure_future(self._asyncio_worker(ctx))
            self._worker_tasks.append(task)

    async def _asyncio_worker(self, ctx: _base.Context) -> None:
        """Receive loop for a single context under asyncio."""
        assert self._queue is not None
        while self._running:
            try:
                data = await ctx.arecv()
                replied_event = asyncio.Event()
                await self._queue.put(Request(data, ctx, _replied_event=replied_event))
                # REP protocol requires reply before next receive on this context.
                await replied_event.wait()
            except Closed:
                break
            except Timeout:
                continue
            except Exception:
                if not self._running:
                    break
                logger.exception("Error in Rep0Service worker")

    async def _start_trio(self) -> None:
        import trio

        send_ch, recv_ch = trio.open_memory_channel(self._workers * 2)
        self._trio_send_channel = send_ch
        self._trio_recv_channel = recv_ch
        self._running = True
        self._contexts = []
        nursery_mgr: _NurseryManagerLike = trio.open_nursery()
        self._nursery_manager = nursery_mgr
        self._nursery = await nursery_mgr.__aenter__()

        assert self._socket is not None
        for _ in range(self._workers):
            ctx = self._socket.new_context()
            self._contexts.append(ctx)
            self._nursery.start_soon(self._trio_worker, ctx)

    async def _trio_worker(self, ctx: _base.Context) -> None:
        """Receive loop for a single context under trio."""
        import trio

        assert self._trio_send_channel is not None
        while self._running:
            try:
                data = await ctx.arecv()
                replied_event: _EventLike = trio.Event()
                await self._trio_send_channel.send(
                    Request(data, ctx, _replied_event=replied_event)
                )
                await replied_event.wait()
            except Closed:
                break
            except Timeout:
                continue
            except Exception:
                if not self._running:
                    break
                logger.exception("Error in Rep0Service worker")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        self._running = False

        try:
            backend = sniffio.current_async_library()
        except sniffio.AsyncLibraryNotFoundError:
            backend = "asyncio"

        if backend == "trio":
            await self._stop_trio()
        else:
            await self._stop_asyncio()

    async def _stop_asyncio(self) -> None:
        for ctx in self._contexts:
            try:
                ctx.close()
            except Exception:
                logger.debug("Exception closing context during shutdown", exc_info=True)

        for task in self._worker_tasks:
            task.cancel()

        for task in self._worker_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Exception in worker during shutdown", exc_info=True)

        if self._queue is not None:
            await self._queue.put(self._sentinel)

        self._worker_tasks.clear()
        self._contexts.clear()

        self._release_socket()

    async def _stop_trio(self) -> None:
        for ctx in self._contexts:
            try:
                ctx.close()
            except Exception:
                logger.debug("Exception closing context during shutdown", exc_info=True)

        assert self._trio_send_channel is not None
        assert self._nursery is not None
        assert self._nursery_manager is not None
        await self._trio_send_channel.aclose()

        self._nursery.cancel_scope.cancel()
        await self._nursery_manager.__aexit__(None, None, None)

        self._contexts.clear()

        self._release_socket()

    def __aiter__(self: _ServiceSelfT) -> _ServiceSelfT:
        return self

    async def __anext__(self) -> Request:
        try:
            backend = sniffio.current_async_library()
        except sniffio.AsyncLibraryNotFoundError:
            backend = "asyncio"

        if backend == "trio":
            import trio

            assert self._trio_recv_channel is not None
            try:
                req: Request = await self._trio_recv_channel.receive()
                return req
            except trio.EndOfChannel:
                raise StopAsyncIteration from None
        else:
            assert self._queue is not None
            item = await self._queue.get()
            if item is self._sentinel:
                raise StopAsyncIteration
            assert isinstance(item, Request)
            return item
