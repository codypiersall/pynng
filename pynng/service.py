"""
High-level async service patterns for common NNG messaging topologies.

Provides ``Rep0Service``, a concurrent request/reply server that manages
multiple NNG contexts behind a simple ``async for`` interface.
"""

import asyncio
import logging
import warnings

import sniffio

import pynng
from .exceptions import Closed


logger = logging.getLogger(__name__)


class Request:
    """A single incoming request received by a :class:`Rep0Service`.

    Attributes:
        data (bytes): The raw request payload.
        context: The :class:`~pynng.Context` that received this request.
            Users should not interact with the context directly; use
            :meth:`reply` instead.

    """

    def __init__(self, data, context, _replied_event=None):
        self.data = data
        self.context = context
        self._replied = False
        self._replied_event = _replied_event

    async def reply(self, data):
        """Send a response back to the requester.

        Args:
            data (bytes): The response payload.

        Raises:
            RuntimeError: If this request has already been replied to.
        """
        if self._replied:
            raise RuntimeError("This request has already been replied to")
        self._replied = True
        await self.context.asend(data)
        if self._replied_event is not None:
            self._replied_event.set()

    def __del__(self):
        if not self._replied:
            warnings.warn(
                "Request with data {!r} was never replied to".format(
                    self.data[:64] if self.data else self.data
                ),
                ResourceWarning,
                stacklevel=1,
            )


class Rep0Service:
    """High-level async REP service that handles concurrent requests.

    Creates a :class:`~pynng.Rep0` socket, listens on the given address,
    and spawns ``workers`` context-based receive loops.  Incoming requests
    are placed into an internal queue and yielded via ``async for``.

    Works with both asyncio and trio.

    Example::

        async with Rep0Service("tcp://0.0.0.0:5555", workers=4) as service:
            async for request in service:
                await request.reply(process(request.data))

    Args:
        address (str): The address to listen on (e.g. ``"tcp://0.0.0.0:5555"``
            or ``"inproc://my-service"``).
        workers (int): Number of concurrent context workers. Each worker can
            handle one request at a time.  Defaults to 4.
        recv_timeout (int or None): Receive timeout in milliseconds for the
            underlying socket.  ``None`` means no timeout.
        send_timeout (int or None): Send timeout in milliseconds for the
            underlying socket.  ``None`` means no timeout.
    """

    def __init__(self, address, *, workers=4, recv_timeout=None, send_timeout=None):
        self._address = address
        self._workers = workers
        self._recv_timeout = recv_timeout
        self._send_timeout = send_timeout
        self._socket = None
        self._contexts = []
        self._queue = None
        self._worker_tasks = []
        self._running = False
        self._sentinel = object()

    async def __aenter__(self):
        kwargs = {}
        if self._recv_timeout is not None:
            kwargs["recv_timeout"] = self._recv_timeout
        if self._send_timeout is not None:
            kwargs["send_timeout"] = self._send_timeout

        self._socket = pynng.Rep0(listen=self._address, **kwargs)

        # Detect async backend
        try:
            backend = sniffio.current_async_library()
        except sniffio.AsyncLibraryNotFoundError:
            backend = "asyncio"

        if backend == "trio":
            await self._start_trio()
        else:
            await self._start_asyncio()

        return self

    async def _start_asyncio(self):
        self._queue = asyncio.Queue()
        self._running = True
        self._contexts = []
        self._worker_tasks = []

        for _ in range(self._workers):
            ctx = self._socket.new_context()
            self._contexts.append(ctx)
            task = asyncio.ensure_future(self._asyncio_worker(ctx))
            self._worker_tasks.append(task)

    async def _asyncio_worker(self, ctx):
        """Receive loop for a single context under asyncio."""
        while self._running:
            try:
                data = await ctx.arecv()
                replied_event = asyncio.Event()
                request = Request(data, ctx, _replied_event=replied_event)
                await self._queue.put(request)
                # Wait for the reply to be sent before receiving the next
                # request on this context (REP protocol requires recv-send
                # alternation per context).
                await replied_event.wait()
            except Closed:
                break
            except Exception:
                if not self._running:
                    break
                logger.exception("Error in Rep0Service worker")

    async def _start_trio(self):
        import trio

        self._trio_send_channel, self._trio_recv_channel = (
            trio.open_memory_channel(self._workers * 2)
        )
        self._running = True
        self._contexts = []
        self._nursery_manager = trio.open_nursery()
        self._nursery = await self._nursery_manager.__aenter__()

        for _ in range(self._workers):
            ctx = self._socket.new_context()
            self._contexts.append(ctx)
            self._nursery.start_soon(self._trio_worker, ctx)

    async def _trio_worker(self, ctx):
        """Receive loop for a single context under trio."""
        import trio

        while self._running:
            try:
                data = await ctx.arecv()
                replied_event = trio.Event()
                request = Request(data, ctx, _replied_event=replied_event)
                await self._trio_send_channel.send(request)
                # Wait for the reply before receiving again on this context
                await replied_event.wait()
            except Closed:
                break
            except Exception:
                if not self._running:
                    break
                logger.exception("Error in Rep0Service worker")

    async def __aexit__(self, *exc_info):
        self._running = False

        try:
            backend = sniffio.current_async_library()
        except sniffio.AsyncLibraryNotFoundError:
            backend = "asyncio"

        if backend == "trio":
            await self._stop_trio()
        else:
            await self._stop_asyncio()

    async def _stop_asyncio(self):
        # Close all contexts first to unblock recv calls
        for ctx in self._contexts:
            try:
                ctx.close()
            except Exception:
                logger.debug("Exception closing context during shutdown", exc_info=True)

        # Cancel worker tasks
        for task in self._worker_tasks:
            task.cancel()

        # Wait for workers to finish
        for task in self._worker_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Exception in worker during shutdown", exc_info=True)

        # Drain the queue
        await self._queue.put(self._sentinel)

        self._worker_tasks.clear()
        self._contexts.clear()

        # Close the socket
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    async def _stop_trio(self):
        # Close all contexts to unblock recv calls
        for ctx in self._contexts:
            try:
                ctx.close()
            except Exception:
                logger.debug("Exception closing context during shutdown", exc_info=True)

        # Close the send channel so workers know to stop
        await self._trio_send_channel.aclose()

        # Cancel the nursery
        self._nursery.cancel_scope.cancel()
        await self._nursery_manager.__aexit__(None, None, None)

        self._contexts.clear()

        # Close the socket
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            backend = sniffio.current_async_library()
        except sniffio.AsyncLibraryNotFoundError:
            backend = "asyncio"

        if backend == "trio":
            import trio

            try:
                return await self._trio_recv_channel.receive()
            except trio.EndOfChannel:
                raise StopAsyncIteration
        else:
            item = await self._queue.get()
            if item is self._sentinel:
                raise StopAsyncIteration
            return item
