"""
Version-independent base classes for pynng.

This module contains the shared base classes that both v1 and v2 protocol
implementations inherit from. All classes use instance-level ``_lib`` and
``_ffi`` attributes instead of module-level globals, enabling the same
code to work with either nng v1 or v2 CFFI bindings.

This is an internal module. Users should import from ``pynng`` (v1) or
``pynng.v2`` (v2).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterable, Iterator
import contextlib
import logging
import math
import os
import threading
import time
from types import TracebackType
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Generic,
    NamedTuple,
    NoReturn,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
    overload,
)
import weakref

import sniffio

from . import _aio, options
from ._finalized import (
    is_nng_finalized as _is_nng_finalized,
    retain_closed as _retain_closed,
)
from .exceptions import Closed, NNGException

if TYPE_CHECKING:
    import cffi

    from . import _nng, _nng_v2
    from .sockaddr import SockAddr  # noqa: F401
    from .tls import TLSConfig

    ReadableBuffer: TypeAlias = bytes | bytearray | memoryview | cffi.FFI.buffer
    WritableBuffer: TypeAlias = bytearray | memoryview
    _NngLib: TypeAlias = _nng._Lib | _nng_v2._Lib
    _NngSocket: TypeAlias = _nng.nng_socket | _nng_v2.nng_socket
    _NngDialer: TypeAlias = _nng.nng_dialer | _nng_v2.nng_dialer
    _NngListener: TypeAlias = _nng.nng_listener | _nng_v2.nng_listener
    _NngPipe: TypeAlias = _nng.nng_pipe | _nng_v2.nng_pipe
    _NngCtx: TypeAlias = _nng.nng_ctx | _nng_v2.nng_ctx
    _NngAio: TypeAlias = _nng.nng_aio | _nng_v2.nng_aio
    _NngMsg: TypeAlias = _nng.nng_msg | _nng_v2.nng_msg
    _SyncRecv: TypeAlias = _nng.pynng_sync_recv_t | _nng_v2.pynng_sync_recv_t
    _OpenerFn: TypeAlias = (
        Callable[[_nng.nng_socket], int]
        | Callable[[_nng_v2.nng_socket], int]
        | Callable[[cffi.FFI.CData], int]
    )
    _CloseFn: TypeAlias = (
        Callable[[_nng.nng_socket], int]
        | Callable[[_nng_v2.nng_socket], int]
        | Callable[[_NngSocket], int]
    )
    _AioFn: TypeAlias = (
        Callable[[_nng.nng_socket, _nng.nng_aio], object]
        | Callable[[_nng_v2.nng_socket, _nng_v2.nng_aio], object]
        | Callable[[_NngSocket | _NngCtx, _NngAio], object]
    )
else:
    ReadableBuffer: TypeAlias = bytes | bytearray | memoryview
    WritableBuffer: TypeAlias = bytearray | memoryview


class _PipeSendChannelLike(Protocol):
    def send_nowait(self, value: PipeEvent[Pipe]) -> None: ...
    def close(self) -> None: ...


class _PipeReceiveChannelLike(Protocol):
    async def receive(self) -> PipeEvent[Pipe]: ...


class _TrioTokenLike(Protocol):
    def run_sync_soon(self, sync_fn: Callable[..., object], *args: object) -> None: ...


class _BaseLibProtocol(Protocol):
    NNG_FLAG_NONBLOCK: int
    NNG_EAGAIN: int
    NNG_ETIMEDOUT: int
    NNG_ECLOSED: int
    NNG_PIPE_EV_ADD_PRE: int
    NNG_PIPE_EV_ADD_POST: int
    NNG_PIPE_EV_REM_POST: int
    _nng_pipe_cb: Callable[[_NngPipe, int, cffi.FFI.CData], None]

    def pynng_sync_recv_alloc(self, recv_p: cffi.FFI.CData) -> int: ...
    def pynng_sync_recv_aio(self, recv: _SyncRecv) -> _NngAio: ...
    def pynng_sync_recv_wait(self, recv: _SyncRecv, slice_ms: int) -> int: ...
    def pynng_sync_recv_free(self, recv: _SyncRecv) -> None: ...
    def nng_aio_alloc(
        self,
        aio_p: cffi.FFI.CData,
        cb: cffi.FFI.CData,
        arg: cffi.FFI.CData,
    ) -> int: ...
    def nng_aio_free(self, aio: _NngAio) -> None: ...
    def nng_aio_set_timeout(self, aio: _NngAio, timeout_ms: int) -> None: ...
    def nng_aio_cancel(self, aio: _NngAio) -> None: ...
    def nng_aio_abort(self, aio: _NngAio, err: int) -> None: ...
    def nng_aio_wait(self, aio: _NngAio) -> None: ...
    def nng_aio_result(self, aio: _NngAio) -> int: ...
    def nng_aio_get_msg(self, aio: _NngAio) -> _NngMsg: ...
    def nng_aio_set_msg(self, aio: _NngAio, msg: _NngMsg | cffi.FFI.CData) -> None: ...
    def nng_socket_id(self, s: _NngSocket) -> int: ...
    def nng_pipe_notify(
        self,
        s: _NngSocket,
        ev: int,
        cb: Callable[[_NngPipe, int, cffi.FFI.CData], None],
        arg: cffi.FFI.CData,
    ) -> int: ...
    def nng_dial(
        self,
        s: _NngSocket,
        addr: cffi.FFI.CData,
        dp: cffi.FFI.CData,
        flags: int,
    ) -> int: ...
    def nng_listen(
        self,
        s: _NngSocket,
        addr: cffi.FFI.CData,
        lp: cffi.FFI.CData,
        flags: int,
    ) -> int: ...
    def nng_close(self, s: _NngSocket) -> int: ...
    def nng_socket_close(self, s: _NngSocket) -> int: ...
    def nng_send(
        self,
        s: _NngSocket,
        data: bytes | cffi.FFI.CData,
        size: int,
        flags: int,
    ) -> int: ...
    def nng_recvmsg(
        self, s: _NngSocket | _NngCtx, msgp: cffi.FFI.CData, flags: int
    ) -> int: ...
    def nng_sendmsg(self, s: _NngSocket, msg: _NngMsg, flags: int) -> int: ...
    def nng_recv_aio(self, s: _NngSocket | _NngCtx, aio: _NngAio) -> object: ...
    def nng_send_aio(self, s: _NngSocket | _NngCtx, aio: _NngAio) -> object: ...
    def nng_device_aio(self, aio: _NngAio, s1: _NngSocket, s2: _NngSocket) -> None: ...
    def nng_dialer_id(self, d: _NngDialer) -> int: ...
    def nng_dialer_close(self, d: _NngDialer) -> int: ...
    def nng_listener_id(self, listener: _NngListener, /) -> int: ...
    def nng_listener_close(self, listener: _NngListener, /) -> int: ...
    def nng_pipe_id(self, p: _NngPipe) -> int: ...
    def nng_pipe_close(self, p: _NngPipe) -> int: ...
    def nng_pipe_dialer(self, p: _NngPipe) -> _NngDialer: ...
    def nng_pipe_listener(self, p: _NngPipe) -> _NngListener: ...
    def nng_ctx_open(self, ctxp: cffi.FFI.CData, s: _NngSocket) -> int: ...
    def nng_ctx_close(self, ctx: _NngCtx) -> int: ...
    def nng_ctx_id(self, ctx: _NngCtx) -> int: ...
    def nng_ctx_recv(self, ctx: _NngSocket | _NngCtx, aio: _NngAio) -> object: ...
    def nng_ctx_send(self, ctx: _NngCtx, aio: _NngAio) -> object: ...
    def nng_ctx_recvmsg(
        self, ctx: _NngSocket | _NngCtx, msgp: cffi.FFI.CData, flags: int
    ) -> int: ...
    def nng_msg_alloc(self, msgp: cffi.FFI.CData, sz: int) -> int: ...
    def nng_msg_free(self, msg: _NngMsg) -> None: ...
    def nng_msg_body(self, msg: _NngMsg) -> cffi.FFI.CData: ...
    def nng_msg_len(self, msg: _NngMsg) -> int: ...
    def nng_msg_append(
        self,
        msg: _NngMsg,
        val: bytes | cffi.FFI.CData,
        sz: int,
    ) -> int: ...
    def nng_msg_header(self, msg: _NngMsg) -> cffi.FFI.CData: ...
    def nng_msg_header_len(self, msg: _NngMsg) -> int: ...
    def nng_msg_header_append(
        self,
        msg: _NngMsg,
        val: bytes | cffi.FFI.CData,
        sz: int,
    ) -> int: ...
    def nng_msg_header_trim(self, msg: _NngMsg, sz: int) -> int: ...
    def nng_msg_header_chop(self, msg: _NngMsg, sz: int) -> int: ...
    def nng_msg_header_clear(self, msg: _NngMsg) -> None: ...
    def nng_msg_get_pipe(self, msg: _NngMsg) -> _NngPipe: ...
    def nng_msg_set_pipe(self, msg: _NngMsg, pipe: _NngPipe) -> int: ...
    def nng_msg_dup(self, dup: cffi.FFI.CData, orig: _NngMsg) -> int: ...


logger = logging.getLogger(__name__)

_GetT = TypeVar("_GetT")
_SetT = TypeVar("_SetT")
_DescSelfT = TypeVar("_DescSelfT")
_PipeT = TypeVar("_PipeT", bound="Pipe", covariant=True)
_SocketSelfT = TypeVar("_SocketSelfT", bound="Socket")
_DialerSelfT = TypeVar("_DialerSelfT", bound="Dialer")
_ListenerSelfT = TypeVar("_ListenerSelfT", bound="Listener")
_ContextSelfT = TypeVar("_ContextSelfT", bound="Context")
_MessageSelfT = TypeVar("_MessageSelfT", bound="Message")

# Keep track of initialized PID to intercept and prevent unsupported fork() calls.
_init_pid: int | None = None
_is_forked_child = False


def _after_fork_in_child() -> None:
    global _is_forked_child
    if _init_pid is not None:
        _is_forked_child = True


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_in_child)


def _mark_nng_initialized() -> None:
    """Record the PID when NNG is initialized."""
    global _init_pid
    if _init_pid is None:
        _init_pid = os.getpid()


def _check_fork() -> None:
    """Verify that we are not executing inside a forked child process.

    NNG is heavily multithreaded and is not fork-reentrant safe.
    Attempting to use NNG in a forked child causes hard C panics or deadlocks.
    """
    if _is_forked_child or (_init_pid is not None and os.getpid() != _init_pid):
        raise RuntimeError(
            "pynng does not support fork(). "
            "NNG background threads and mutexes cannot survive a fork without exec. "
            "Use multiprocessing.set_start_method('spawn') instead."
        )


# Live sockets by (version tag, socket id). No lock guards it: Socket.__del__
# updates it, and a finalizer can run while its thread holds any lock. Each
# update is one dict operation on a key that only the calling socket can own.
_active_handles: dict[tuple[str | None, int], weakref.ReferenceType[Socket]] = {}

# Guards Socket._device_aios and the start and end of every device aio. Take
# it only through _device_section().
_device_lock = threading.Lock()


@contextlib.contextmanager
def _device_section() -> Iterator[None]:
    # The mark is set before the lock is taken and cleared after it is
    # released, so it covers all of the time this thread holds the lock.
    state = _aio._device_section_thread
    depth = getattr(state, "depth", 0)
    state.depth = depth + 1
    try:
        with _device_lock:
            yield
    finally:
        state.depth = depth


if TYPE_CHECKING:

    class PipeEvent(tuple[_PipeT, str], Generic[_PipeT]):
        """A pipe event with the pipe and the event type.

        Attributes:
            pipe: The :class:`Pipe` associated with the event.
            event_type: One of ``"pre_add"``, ``"post_add"``, or ``"remove"``.
        """

        pipe: _PipeT
        event_type: str

        def __new__(cls, pipe: _PipeT, event_type: str) -> PipeEvent[_PipeT]:
            return super().__new__(cls, (pipe, event_type))

else:

    class _PipeEventTuple(NamedTuple):
        pipe: Pipe
        event_type: str

    class PipeEvent(_PipeEventTuple, Generic[_PipeT]):
        """A pipe event with the pipe and the event type.

        Attributes:
            pipe: The :class:`Pipe` associated with the event.
            event_type: One of ``"pre_add"``, ``"post_add"``, or ``"remove"``.
        """

        __slots__ = ()


_SENTINEL = object()
_RECV_SLICE_MS = 100  # Slice duration for interruptable recv loop (ms)


# sched_yield releases the GIL and gives up the CPU without a timed sleep, which
# on Linux is subject to timer slack. Windows has no sched_yield; there
# time.sleep(0) maps to Sleep(0), also a plain yield.
_yield_cpu: Callable[[], None] = getattr(os, "sched_yield", None) or (
    lambda: time.sleep(0)
)


def _sliced_aio_recv(
    recv_fn: Callable[[_NngSocket | _NngCtx, _NngAio], object],
    target_handle: _NngSocket | _NngCtx,
    lib: _NngLib,
    ffi: cffi.FFI,
    timeout_ms: int | None,
    slice_ms: int = _RECV_SLICE_MS,
    nonblock_recv_fn: Callable[[_NngSocket | _NngCtx, cffi.FFI.CData, int], int]
    | None = None,
) -> _NngMsg:
    """Perform an interruptable receive with a single nng_aio.

    CFFI releases the GIL when blocking in C. If a thread waits in a long or
    infinite C wait (e.g. pthread_cond_wait), Python signal handlers (such as
    KeyboardInterrupt on Ctrl-C) are never triggered until C returns. So the
    wait for the aio is sliced into short intervals (default 100ms), and
    Python's runtime runs pending signal handlers between them. The aio
    completion is signalled in C, so it does not take the GIL.

    The aio stays in flight between slices. Cancelling a receive aborts a Req0
    request and ends a Surveyor0 survey, so the aio is cancelled only when the
    wait is interrupted. nng enforces ``timeout_ms`` and protocol deadlines
    (such as the survey time) and reports both as ``NNG_ETIMEDOUT``.

    A message that is already queued is first taken with ``nonblock_recv_fn``,
    which completes on the calling thread. nng runs the callback of an aio on
    a task queue thread, so a message taken with the aio costs two thread
    switches.

    Args:
        recv_fn: C function to initiate receive (e.g. nng_recv_aio,
            nng_socket_recv, nng_ctx_recv).
        target_handle: CFFI socket or context handle.
        lib: CFFI library instance.
        ffi: CFFI ffi instance.
        timeout_ms: Total timeout in milliseconds (-1 or None for infinite).
        slice_ms: Slice interval in milliseconds.
        nonblock_recv_fn: ``nng_recvmsg`` or ``nng_ctx_recvmsg``, or None to
            not take a queued message first.

    Returns:
        nng_msg*: Pointer to received C message.
    """
    from .exceptions import check_err

    base_lib = cast(_BaseLibProtocol, lib)
    if timeout_ms is None or timeout_ms < 0:
        timeout_ms = -1

    if nonblock_recv_fn is not None:
        msg_p = ffi.new("nng_msg **")
        rv = nonblock_recv_fn(target_handle, msg_p, base_lib.NNG_FLAG_NONBLOCK)
        if rv == 0:
            return cast("_NngMsg", msg_p[0])
        if rv != base_lib.NNG_EAGAIN:
            check_err(rv, lib=lib, ffi=ffi)
        if timeout_ms == 0:
            check_err(base_lib.NNG_ETIMEDOUT, lib=lib, ffi=ffi)
        # Over inproc, nng moves a message on its own threads, so it is often
        # in flight when recv() is called. One yield lets it land, and the
        # retry then avoids the aio callback's extra task queue switch.
        _yield_cpu()
        rv = nonblock_recv_fn(target_handle, msg_p, base_lib.NNG_FLAG_NONBLOCK)
        if rv == 0:
            return cast("_NngMsg", msg_p[0])
        if rv != base_lib.NNG_EAGAIN:
            check_err(rv, lib=lib, ffi=ffi)

    recv_p = ffi.new("pynng_sync_recv_t **")
    check_err(base_lib.pynng_sync_recv_alloc(recv_p), lib=lib, ffi=ffi)
    recv = cast("_SyncRecv", recv_p[0])
    try:
        aio = base_lib.pynng_sync_recv_aio(recv)
        base_lib.nng_aio_set_timeout(aio, timeout_ms)
        recv_fn(target_handle, aio)
        try:
            while not base_lib.pynng_sync_recv_wait(recv, slice_ms):
                pass
        except BaseException:
            base_lib.nng_aio_cancel(aio)
            base_lib.nng_aio_wait(aio)
            if base_lib.nng_aio_result(aio) == 0:
                base_lib.nng_msg_free(base_lib.nng_aio_get_msg(aio))
                base_lib.nng_aio_set_msg(aio, ffi.NULL)
            raise
        check_err(base_lib.nng_aio_result(aio), lib=lib, ffi=ffi)
        raw_msg = base_lib.nng_aio_get_msg(aio)
        base_lib.nng_aio_set_msg(aio, ffi.NULL)
        return raw_msg
    finally:
        base_lib.pynng_sync_recv_free(recv)


def _ensure_can_send(thing: object) -> None:
    """
    It's easy to accidentally pass in a str instead of bytes when send()ing.
    This gives a more informative message if a ``str`` was accidentally passed
    to a send method.

    """
    _check_fork()
    if isinstance(thing, str):
        raise ValueError(
            'Cannot send type str. Maybe you left out a ".encode()" somewhere?'
        )


def to_char(
    charlike: str | bytes | os.PathLike[str] | cffi.FFI.CData,
    add_null_term: bool = False,
    ffi: cffi.FFI | None = None,
) -> cffi.FFI.CData:
    """Convert str or bytes to char*.

    Args:
        charlike: The string-like object to convert.
        add_null_term: Whether to add a null terminator.
        ffi: The CFFI ffi instance to use. If None, uses v1's ffi.
    """
    if ffi is None:
        from ._nng import ffi as _ffi

        ffi = _ffi
    if isinstance(charlike, os.PathLike):
        charlike = os.fsdecode(charlike)
    if isinstance(charlike, str):
        charlike = charlike.encode()
    if isinstance(charlike, bytes):
        if add_null_term:
            charlike = charlike + b"\x00"
        return ffi.new("char[]", charlike)
    return charlike


_pipe_callback_thread = threading.local()


def _in_pipe_callback() -> bool:
    """Return True if the current thread is running a pipe callback."""
    return getattr(_pipe_callback_thread, "depth", 0) > 0


def _do_callbacks(pipe: Pipe, callbacks: Iterable[Callable[[Pipe], object]]) -> None:
    _pipe_callback_thread.depth = getattr(_pipe_callback_thread, "depth", 0) + 1
    try:
        for cb in callbacks:
            try:
                cb(pipe)
            except Exception:
                msg = "Exception raised in pre pipe connect callback {!r}"
                logger.exception(msg.format(cb))
    finally:
        _pipe_callback_thread.depth -= 1


class _PipeState:
    """Dispatcher bookkeeping for one pipe, from its first event to REM_POST."""

    __slots__ = ("added", "pipe", "rejected", "removing", "running")

    def __init__(self, pipe: Pipe) -> None:
        self.pipe = pipe
        # Idents of threads currently running callbacks for this pipe.
        self.running: list[int] = []
        self.added = False
        self.rejected = False
        self.removing = False


def _handle_pipe_event(
    sock: Socket, lib_pipe: _NngPipe, event: int, lib: _NngLib
) -> None:
    """Pipe event dispatcher shared by the v1 and v2 callbacks.

    nng v1 can deliver ``NNG_PIPE_EV_REM_POST`` on its reaper thread before
    ``NNG_PIPE_EV_ADD_PRE`` or ``NNG_PIPE_EV_ADD_POST`` for the same pipe. So
    ``post_pipe_remove`` waits for the running connect callbacks of that pipe,
    and an ADD event that arrives after ``REM_POST`` is dropped. Callbacks run without the pipe lock held, so they
    can read ``Socket.pipes``.

    A callback must not wait for a later callback of the same pipe, because
    that later callback waits for it to return. For this reason
    :meth:`Socket.close` called from a pipe callback does not wait for the
    socket to finish closing.
    """
    base_lib = cast(_BaseLibProtocol, lib)
    pipe_id = base_lib.nng_pipe_id(lib_pipe)
    me = threading.get_ident()
    cond = sock._pipe_notify_cond
    with cond:
        if pipe_id in sock._removed_pipe_ids:
            return
        state = sock._pipe_states.get(pipe_id)
        if event == base_lib.NNG_PIPE_EV_REM_POST:
            if state is None:
                # REM_POST overtook ADD_PRE; ADD_PRE must not resurrect it.
                sock._remember_removed_pipe_id(pipe_id)
                logger.debug("Could not find pipe for socket")
                return
            if state.removing:
                return
            state.removing = True
            if not state.added:
                sock._remember_removed_pipe_id(pipe_id)
            while any(t != me for t in state.running):
                cond.wait()
            callbacks = [] if state.rejected else list(sock._on_post_pipe_remove)
        elif event == base_lib.NNG_PIPE_EV_ADD_PRE:
            if state is not None:
                return
            pipe_cls = sock._pipe_class or Pipe
            state = _PipeState(pipe_cls(lib_pipe, sock))
            sock._pipe_states[pipe_id] = state
            sock._pipes[pipe_id] = state.pipe
            callbacks = list(sock._on_pre_pipe_add)
        elif event == base_lib.NNG_PIPE_EV_ADD_POST:
            if state is None:
                pipe_cls = sock._pipe_class or Pipe
                state = _PipeState(pipe_cls(lib_pipe, sock))
                sock._pipe_states[pipe_id] = state
            elif state.removing or state.added or state.rejected:
                return
            state.added = True
            sock._pipes[pipe_id] = state.pipe
            callbacks = list(sock._on_post_pipe_add)
        else:
            return
        state.running.append(me)
        pipe = state.pipe

    try:
        _do_callbacks(pipe, callbacks)
    finally:
        with cond:
            state.running.remove(me)
            if event == base_lib.NNG_PIPE_EV_REM_POST:
                if sock._pipe_states.get(pipe_id) is state:
                    del sock._pipe_states[pipe_id]
                    sock._pipes.pop(pipe_id, None)
            elif (
                event == base_lib.NNG_PIPE_EV_ADD_PRE
                and sock._pipe_states.get(pipe_id) is state
                and not state.added
                and pipe.closed
            ):
                state.rejected = True
                sock._pipes.pop(pipe_id, None)
            cond.notify_all()


class PipeEventStream(AsyncIterator[PipeEvent[_PipeT]], Generic[_PipeT]):
    """Async iterator that yields :class:`PipeEvent` objects.

    Returned by :meth:`Socket.pipe_events`.  Use it with ``async for``::

        async for event in socket.pipe_events():
            print(f"Pipe {event.pipe} {event.event_type}")

    Call :meth:`close` or use ``async with`` to stop receiving events and
    unregister the internal callbacks.
    """

    def __init__(self, socket: Socket) -> None:
        self._socket = socket
        self._closed = False
        backend = socket._async_backend
        if backend is None:
            backend = sniffio.current_async_library()
        self._backend = backend

        if self._backend == "asyncio":
            self._queue: asyncio.Queue[PipeEvent[_PipeT] | object] = asyncio.Queue()
            self._loop = asyncio.get_running_loop()
        elif self._backend == "trio":
            import trio

            send_ch, recv_ch = trio.open_memory_channel[PipeEvent[Pipe]](math.inf)
            self._send_channel: _PipeSendChannelLike = send_ch
            self._receive_channel: _PipeReceiveChannelLike = recv_ch
            self._trio_token: _TrioTokenLike = trio.lowlevel.current_trio_token()
        else:
            raise ValueError(f"The async backend {backend} is not currently supported.")

        # Register callbacks
        self._socket.add_pre_pipe_connect_cb(self._on_pre_add)
        self._socket.add_post_pipe_connect_cb(self._on_post_add)
        self._socket.add_post_pipe_remove_cb(self._on_remove)

    def _put_event(self, event: PipeEvent[Pipe]) -> None:
        """Thread-safe put of an event into the async queue."""
        if self._closed:
            return
        if self._backend == "asyncio":
            self._loop.call_soon_threadsafe(
                self._queue.put_nowait, cast("PipeEvent[_PipeT]", event)
            )
        elif self._backend == "trio":
            self._trio_token.run_sync_soon(
                self._trio_send_nowait,
                event,
            )

    def _trio_send_nowait(self, event: PipeEvent[Pipe]) -> None:
        """Wrapper for send_nowait that suppresses ClosedResourceError.

        Called via ``run_sync_soon`` from a foreign thread, so any exception
        raised here would crash the Trio event loop.
        """
        import trio

        try:
            self._send_channel.send_nowait(event)
        except trio.ClosedResourceError:
            pass

    def _on_pre_add(self, pipe: Pipe) -> None:
        ev_cls = self._socket._pipe_event_class or PipeEvent
        self._put_event(ev_cls(pipe=pipe, event_type="pre_add"))

    def _on_post_add(self, pipe: Pipe) -> None:
        ev_cls = self._socket._pipe_event_class or PipeEvent
        self._put_event(ev_cls(pipe=pipe, event_type="post_add"))

    def _on_remove(self, pipe: Pipe) -> None:
        ev_cls = self._socket._pipe_event_class or PipeEvent
        self._put_event(ev_cls(pipe=pipe, event_type="remove"))

    def close(self) -> None:
        """Stop receiving events and unregister callbacks."""
        if self._closed:
            return
        self._closed = True

        # Unregister callbacks
        try:
            self._socket.remove_pre_pipe_connect_cb(self._on_pre_add)
        except ValueError:
            pass
        try:
            self._socket.remove_post_pipe_connect_cb(self._on_post_add)
        except ValueError:
            pass
        try:
            self._socket.remove_post_pipe_remove_cb(self._on_remove)
        except ValueError:
            pass

        # Signal the iterator to stop
        if self._backend == "asyncio":
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, _SENTINEL)
            except RuntimeError:
                # Loop may be closed already
                pass
        elif self._backend == "trio":
            import trio

            try:
                self._send_channel.close()
            except trio.ClosedResourceError:
                pass

    def __aiter__(self) -> PipeEventStream[_PipeT]:
        return self

    async def __anext__(self) -> PipeEvent[_PipeT]:
        if self._closed:
            raise StopAsyncIteration
        if self._backend == "asyncio":
            item = await self._queue.get()
            if item is _SENTINEL:
                raise StopAsyncIteration
            assert isinstance(item, PipeEvent)
            return cast("PipeEvent[_PipeT]", item)
        elif self._backend == "trio":
            import trio

            try:
                return cast("PipeEvent[_PipeT]", await self._receive_channel.receive())
            except trio.EndOfChannel:
                raise StopAsyncIteration
        raise StopAsyncIteration

    async def __aenter__(self) -> PipeEventStream[_PipeT]:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


# --- Option descriptors ---
# These descriptors call into options.py, which resolves lib/ffi from the
# owning instance.


class _NNGOption(Generic[_GetT, _SetT]):
    """A descriptor for more easily getting/setting NNG option."""

    # this class should not be instantiated directly!  Instantiation will work,
    # but getting/setting will fail.

    # subclasses set _getter and _setter to the module-level getter and setter
    # functions
    _getter: Callable[[_OptionTarget, str | bytes], _GetT] | None = None
    _setter: Callable[[_OptionTarget, str | bytes, _SetT], None] | None = None

    def __init__(self, option_name: str | bytes) -> None:
        self.option = to_char(option_name)

    @overload
    def __get__(
        self: _DescSelfT,
        instance: None,
        owner: type[_OptionTarget] | None = None,
    ) -> _DescSelfT: ...

    @overload
    def __get__(
        self,
        instance: _OptionTarget,
        owner: type[_OptionTarget] | None = None,
    ) -> _GetT: ...

    def __get__(
        self,
        instance: _OptionTarget | None,
        owner: type[_OptionTarget] | None = None,
    ) -> object:
        if instance is None:
            return self
        # have to look up the getter on the class
        getter = self.__class__._getter
        if getter is None:
            raise TypeError(f"{self.__class__} is write-only")
        return getter(instance, cast("str | bytes", self.option))

    def __set__(self, instance: _OptionTarget, value: _SetT) -> None:
        setter = self.__class__._setter
        if setter is None:
            raise TypeError(f"{self.__class__} is readonly")
        setter(instance, cast("str | bytes", self.option), value)


class _ReadOnlyOption(_NNGOption[_GetT, NoReturn]):
    """Base descriptor for read-only nng options."""


class IntOption(_NNGOption[int, int]):
    """Descriptor for getting/setting integer options"""

    _getter = staticmethod(options._getopt_int)
    _setter = staticmethod(options._setopt_int)


class ReadOnlyIntOption(_ReadOnlyOption[int]):
    """Descriptor for getting read-only integer options"""

    _getter = staticmethod(options._getopt_int)


class MsOption(_NNGOption[int, int]):
    """Descriptor for getting/setting durations (in milliseconds)"""

    _getter = staticmethod(options._getopt_ms)
    _setter = staticmethod(options._setopt_ms)


class SockAddrOption(_ReadOnlyOption["SockAddr"]):
    """Descriptor for getting read-only socket address options"""

    _getter = staticmethod(options._getopt_sockaddr)


class SizeOption(_NNGOption[int, int]):
    """Descriptor for getting/setting size_t options"""

    _getter = staticmethod(options._getopt_size)
    _setter = staticmethod(options._setopt_size)


class StringOption(_NNGOption[str, str | bytes]):
    """Descriptor for getting/setting string options"""

    _getter = staticmethod(options._getopt_string)
    _setter = staticmethod(options._setopt_string)


class ReadOnlyStringOption(_ReadOnlyOption[str]):
    """Descriptor for getting read-only string options"""

    _getter = staticmethod(options._getopt_string)


class BooleanOption(_NNGOption[bool, bool]):
    """Descriptor for getting/setting boolean values"""

    _getter = staticmethod(options._getopt_bool)
    _setter = staticmethod(options._setopt_bool)


class ReadOnlyBooleanOption(_ReadOnlyOption[bool]):
    """Descriptor for getting read-only boolean values"""

    _getter = staticmethod(options._getopt_bool)


class PointerOption:
    """Descriptor for setting write-only pointer values"""

    _setter = staticmethod(options._setopt_ptr)

    def __init__(self, option_name: str | bytes) -> None:
        self.option = to_char(option_name)

    # Intentionally typed with instance: None so mypy --strict rejects reading
    # write-only s.tls_config with [arg-type] without marking code unreachable.
    def __get__(
        self,
        instance: None,
        owner: type[_OptionTarget] | None = None,
    ) -> PointerOption:
        if instance is None:
            return self
        raise TypeError(f"{self.__class__} is write-only")

    def __set__(self, instance: _OptionTarget, value: TLSConfig) -> None:
        self.__class__._setter(instance, cast("str | bytes", self.option), value)
        if instance is not None and value is not None:
            if not hasattr(instance, "_pointer_option_refs"):
                setattr(instance, "_pointer_option_refs", {})
            refs = cast(
                "dict[cffi.FFI.CData, TLSConfig]",
                getattr(instance, "_pointer_option_refs"),
            )
            refs[self.option] = value
            _retain_closed(value)


class NotImplementedOption(_NNGOption[NoReturn, NoReturn]):
    """Represents a currently un-implemented option in Python."""

    def __init__(self, option_name: str | bytes, errmsg: str) -> None:
        super().__init__(option_name)
        self.errmsg = errmsg

    @overload
    def __get__(
        self,
        instance: None,
        owner: type[_OptionTarget] | None = None,
    ) -> NotImplementedOption: ...

    @overload
    def __get__(
        self,
        instance: _OptionTarget,
        owner: type[_OptionTarget] | None = None,
    ) -> NoReturn: ...

    def __get__(
        self,
        instance: _OptionTarget | None,
        owner: type[_OptionTarget] | None = None,
    ) -> NotImplementedOption:
        if instance is None:
            return self
        raise NotImplementedError(self.errmsg)

    def __set__(self, instance: _OptionTarget, value: object) -> NoReturn:
        raise NotImplementedError(self.errmsg)


# --- Base classes ---


class Socket:
    """Base socket class. Version-specific subclasses must set _lib and _ffi.

    This should not be instantiated directly; use protocol subclasses from
    ``pynng`` (v1) or ``pynng.v2`` (v2).
    """

    # Subclasses MUST set these to the appropriate CFFI lib and ffi.
    _lib: ClassVar[_NngLib]
    _ffi: ClassVar[cffi.FFI]

    # Version tag for _active_handles keys. Prevents ID collision between
    # v1 and v2 sockets.
    _version_tag: str | None = None
    # Surveyor0 sets this False: nng extends a zero recv timeout to the end
    # of the survey (surv0_ctx_recv), so a nonblocking recv can block.
    _nonblock_recv_first: bool = True
    _opener: _OpenerFn | None = None
    _raw_opener: _OpenerFn | None = None

    @property
    def _aio_recv_fn(self) -> _AioFn | None:
        return None

    @property
    def _aio_send_fn(self) -> _AioFn | None:
        return None

    # the following options correspond to nng options documented at
    # https://nanomsg.github.io/nng/man/v1.0.1/nng_options.5.html
    recv_buffer_size = IntOption("recv-buffer")
    send_buffer_size = IntOption("send-buffer")
    recv_timeout = MsOption("recv-timeout")
    send_timeout = MsOption("send-timeout")
    ttl_max = IntOption("ttl-max")
    recv_max_size = SizeOption("recv-size-max")
    reconnect_time_min = MsOption("reconnect-time-min")
    reconnect_time_max = MsOption("reconnect-time-max")
    tcp_nodelay = BooleanOption("tcp-nodelay")
    tcp_keepalive = BooleanOption("tcp-keepalive")

    def __init__(
        self,
        *,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
    ) -> None:
        _check_fork()
        _mark_nng_initialized()

        # mapping of id: Python objects
        self._dialers: dict[int, Dialer] = {}
        self._listeners: dict[int, Listener] = {}
        self._pipes: dict[int, Pipe] = {}
        self._pipe_states: dict[int, _PipeState] = {}
        self._removed_pipe_ids: dict[int, None] = {}
        self._on_pre_pipe_add: list[Callable[[Pipe], object]] = []
        self._on_post_pipe_add: list[Callable[[Pipe], object]] = []
        self._on_post_pipe_remove: list[Callable[[Pipe], object]] = []
        self._pipe_notify_lock = threading.Lock()
        self._pipe_notify_cond = threading.Condition(self._pipe_notify_lock)
        self._socket_closed = False
        self._close_lock = threading.Lock()
        # nng_aio of each device running on this socket. nng v2 refuses to
        # close a socket that a device owns, so close() must end the device.
        self._device_aios: set[_NngAio] = set()
        self._async_backend = async_backend
        self._recv_pool: list[_aio.AIOHelper] = []
        self._send_pool: list[_aio.AIOHelper] = []

        _ffi = self._ffi

        self._socket = _ffi.new(
            "nng_socket *",
        )
        if opener is not None:
            self._opener = opener
        elif raw and getattr(self, "_raw_opener", None) is not None:
            self._opener = self._raw_opener
        elif getattr(self, "_opener", None) is None:
            raise TypeError("Cannot directly instantiate a Socket.  Try a subclass.")
        assert self._opener is not None
        from .exceptions import check_err

        opener_fn = cast("Callable[[cffi.FFI.CData], int]", self._opener)
        check_err(opener_fn(self._socket))

        if recv_timeout is not None:
            self.recv_timeout = recv_timeout
        if send_timeout is not None:
            self.send_timeout = send_timeout
        if recv_max_size is not None:
            self.recv_max_size = recv_max_size
        if reconnect_time_min is not None:
            self.reconnect_time_min = reconnect_time_min
        if reconnect_time_max is not None:
            self.reconnect_time_max = reconnect_time_max
        if recv_buffer_size is not None:
            self.recv_buffer_size = recv_buffer_size
        if send_buffer_size is not None:
            self.send_buffer_size = send_buffer_size

        # set up pipe callbacks. This **must** be called before listen/dial to
        # avoid race conditions.
        self._setup_pipe_callbacks()
        self._configure_protocol_options()

        if listen is not None:
            self.listen(listen)
        if dial is not None:
            self.dial(dial, block=block_on_dial)

    def _configure_protocol_options(self) -> None:
        """Hook for protocol subclasses to apply options before listen/dial."""

    def _setup_pipe_callbacks(self) -> None:
        """Register pipe notification callbacks with NNG."""
        _ffi = self._ffi
        base_lib = cast(_BaseLibProtocol, self._lib)

        handle = _ffi.new_handle(self)
        self._handle = handle
        key = (self._version_tag, int(base_lib.nng_socket_id(self.socket)))
        _active_handles[key] = weakref.ref(self)

        for event in (
            base_lib.NNG_PIPE_EV_ADD_PRE,
            base_lib.NNG_PIPE_EV_ADD_POST,
            base_lib.NNG_PIPE_EV_REM_POST,
        ):
            from .exceptions import check_err

            check_err(
                base_lib.nng_pipe_notify(
                    self.socket, event, base_lib._nng_pipe_cb, handle
                )
            )

    def dial(self, address: str | bytes, *, block: bool | None = None) -> Dialer:
        """Dial the specified address.

        Args:
            address:  The address to dial.
            block:  Whether to block or not.  There are three possible values
              this can take:

                1. If ``True``, a blocking dial is attempted.  If it fails for
                   any reason, the dial fails and an exception is raised.
                2. If ``False``, a non-blocking dial is started.  The dial is
                   retried periodically in the background until it is
                   successful.
                3. (**Default behavior**): If ``None``, a blocking dial is
                   first attempted. If it fails an exception is logged (using
                   the Python logging module), then a non-blocking dial is
                   done.

        """
        _check_fork()
        import pynng

        if block:
            return self._dial(address, flags=0)
        elif block is None:
            try:
                return self.dial(address, block=True)
            except pynng.ConnectionRefused:
                msg = "Synchronous dial failed; attempting asynchronous now"
                logger.exception(msg)
                return self.dial(address, block=False)
        else:
            return self._dial(address, flags=self._lib.NNG_FLAG_NONBLOCK)

    def _dial(self, address: str | bytes, flags: int = 0) -> Dialer:
        """Dial specified ``address``

        ``flags`` usually do not need to be given.

        """
        _ffi = self._ffi
        base_lib = cast(_BaseLibProtocol, self._lib)
        from .exceptions import check_err

        dialer = _ffi.new("nng_dialer *")
        ret = base_lib.nng_dial(self.socket, to_char(address, ffi=_ffi), dialer, flags)
        check_err(ret)
        # we can only get here if check_err doesn't raise
        d_id = int(base_lib.nng_dialer_id(cast("_NngDialer", dialer[0])))
        dialer_cls = self._dialer_class or Dialer
        py_dialer = dialer_cls(dialer, self)
        self._dialers[d_id] = py_dialer
        return py_dialer

    def listen(self, address: str | bytes, flags: int = 0) -> Listener:
        """Listen at specified address.

        ``listener`` and ``flags`` usually do not need to be given.

        """
        _check_fork()
        _ffi = self._ffi
        base_lib = cast(_BaseLibProtocol, self._lib)
        from .exceptions import check_err

        listener = _ffi.new("nng_listener *")
        ret = base_lib.nng_listen(
            self.socket, to_char(address, ffi=_ffi), listener, flags
        )
        check_err(ret)
        # we can only get here if check_err doesn't raise
        l_id = int(base_lib.nng_listener_id(cast("_NngListener", listener[0])))
        listener_cls = self._listener_class or Listener
        py_listener = listener_cls(listener, self)
        self._listeners[l_id] = py_listener
        return py_listener

    def close(self) -> None:
        """Close the socket, freeing all system resources."""
        base_lib = cast(_BaseLibProtocol, self._lib)
        if self._lib is not None and hasattr(self._lib, "nng_close"):
            self._do_close(base_lib.nng_close)
        elif self._lib is not None and hasattr(self._lib, "nng_socket_close"):
            self._do_close(base_lib.nng_socket_close)

    def recv(self, block: bool = True) -> bytes:
        """Receive data on the socket."""
        msg = self.recv_msg(block=block)
        return msg.bytes

    def send(self, data: ReadableBuffer, block: bool = True) -> None:
        """Send data on the socket."""
        _ensure_can_send(data)
        _lib = self._lib
        _ffi = self._ffi
        base_lib = cast(_BaseLibProtocol, _lib)
        from .exceptions import check_err

        flags = 0
        if not block:
            flags |= base_lib.NNG_FLAG_NONBLOCK
        c_buf: bytes | cffi.FFI.CData
        if isinstance(data, bytes):
            c_buf = data
        else:
            c_buf = _ffi.from_buffer(data)
        err = base_lib.nng_send(self.socket, c_buf, len(data), flags)
        check_err(err, lib=_lib, ffi=_ffi)

    async def arecv(self) -> bytes:
        """Asynchronously receive data on the socket."""
        msg = await self.arecv_msg()
        return msg.bytes

    async def asend(self, data: ReadableBuffer) -> None:
        """Asynchronously send data on the socket."""
        _ensure_can_send(data)
        helper = self._acquire_send_helper()
        try:
            return await helper.asend(data)
        finally:
            self._release_send_helper(helper)

    def _do_close(self, close_fn: _CloseFn) -> None:
        """Common close pattern used by both v1 and v2.

        ``close_fn`` waits for running pipe callbacks to return, so a close
        from a pipe callback returns at once and the socket is closed on
        another thread. The same applies to a close in a device section,
        which is a finalizer that runs while its thread can hold the device
        lock.

        Args:
            close_fn: The NNG close function to call (e.g. lib.nng_close or
                lib.nng_socket_close).
        """
        if not hasattr(self, "_socket"):
            return
        with self._close_lock:
            if self._socket_closed:
                return
            self._socket_closed = True
        if _in_pipe_callback() or _aio._in_device_section():
            threading.Thread(
                target=self._finish_close, args=(close_fn,), name="pynng-close"
            ).start()
        else:
            self._finish_close(close_fn)

    def _finish_close(self, close_fn: _CloseFn) -> None:
        self._end_devices()
        base_lib = cast(_BaseLibProtocol, self._lib)
        key = (self._version_tag, int(base_lib.nng_socket_id(self.socket)))
        # Deregister before close_fn: until then nng cannot give this id to
        # another socket, so no other thread writes this key.
        ref = _active_handles.get(key)
        if ref is not None and (ref() is self or ref() is None):
            _active_handles.pop(key, None)
        cast("Callable[[_NngSocket], int]", close_fn)(self.socket)
        self._listeners = {}
        self._dialers = {}
        while self._recv_pool:
            self._recv_pool.pop()._free()
        while self._send_pool:
            self._send_pool.pop()._free()

    def _end_devices(self) -> None:
        """End the devices on this socket; nng closes the sockets they own."""
        base_lib = cast(_BaseLibProtocol, self._lib)
        with _device_section():
            aios = list(self._device_aios)
            for aio in aios:
                base_lib.nng_aio_abort(aio, base_lib.NNG_ECLOSED)
            # A device is done, and has closed its sockets, when its aio is.
            for aio in aios:
                base_lib.nng_aio_wait(aio)

    def __del__(self) -> None:
        if _is_nng_finalized():
            return
        try:
            self.close()
        except (TypeError, AttributeError):
            pass

    @property
    def socket(self) -> _NngSocket:
        return cast("_NngSocket", self._socket[0])

    def recv_msg(self, block: bool = True) -> Message:
        """Receive a :class:`Message` on the socket."""
        _check_fork()
        _ffi = self._ffi
        _lib = self._lib
        base_lib = cast(_BaseLibProtocol, _lib)
        from .exceptions import check_err

        if not block:
            flags = base_lib.NNG_FLAG_NONBLOCK
            msg_p = _ffi.new("nng_msg **")
            check_err(
                base_lib.nng_recvmsg(self.socket, msg_p, flags),
                lib=_lib,
                ffi=_ffi,
            )
            raw_msg = cast("_NngMsg", msg_p[0])
        else:
            recv_fn: Callable[[_NngSocket | _NngCtx, _NngAio], object]
            if self._aio_recv_fn is not None:
                recv_fn = cast(
                    "Callable[[_NngSocket | _NngCtx, _NngAio], object]",
                    self._aio_recv_fn,
                )
            else:
                recv_fn = base_lib.nng_recv_aio
            timeout = self.recv_timeout
            raw_msg = _sliced_aio_recv(
                recv_fn,
                self.socket,
                _lib,
                _ffi,
                timeout,
                nonblock_recv_fn=(
                    base_lib.nng_recvmsg if self._nonblock_recv_first else None
                ),
            )

        msg_cls = self._message_class or Message
        msg = msg_cls(raw_msg, _lib=_lib, _ffi=_ffi)
        self._try_associate_msg_with_pipe(msg)
        return msg

    def recv_into(self, buffer: WritableBuffer, block: bool = True) -> int:
        """Receive data directly into the provided writable buffer.

        Args:
            buffer: A writable buffer object (e.g. bytearray, memoryview).
            block: If False, raises pynng.TryAgain immediately if no data is available.

        Returns:
            int: The number of bytes written to buffer.
        """
        _check_fork()
        m = memoryview(buffer)
        if m.readonly:
            raise BufferError("buffer must be writable")
        msg = self.recv_msg(block=block)
        base_lib = cast(_BaseLibProtocol, self._lib)
        with msg._mem_freed_lock:
            body = base_lib.nng_msg_body(msg._nng_msg)
            msg_len = int(base_lib.nng_msg_len(msg._nng_msg))
            nbytes = min(len(m), msg_len)
            c_buf = self._ffi.from_buffer(m)
            self._ffi.memmove(c_buf, body, nbytes)
        return nbytes

    async def arecv_into(self, buffer: WritableBuffer) -> int:
        """Asynchronously receive data directly into the provided writable buffer.

        Args:
            buffer: A writable buffer object (e.g. bytearray, memoryview).

        Returns:
            int: The number of bytes written to buffer.
        """
        m = memoryview(buffer)
        if m.readonly:
            raise BufferError("buffer must be writable")
        msg = await self.arecv_msg()
        base_lib = cast(_BaseLibProtocol, self._lib)
        with msg._mem_freed_lock:
            body = base_lib.nng_msg_body(msg._nng_msg)
            msg_len = int(base_lib.nng_msg_len(msg._nng_msg))
            nbytes = min(len(m), msg_len)
            c_buf = self._ffi.from_buffer(m)
            self._ffi.memmove(c_buf, body, nbytes)
        return nbytes

    def recv_nowait(self) -> bytes:
        """Receive data on the socket without blocking.

        Equivalent to ``recv(block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv(block=False)

    def send_nowait(self, data: ReadableBuffer) -> None:
        """Send data on the socket without blocking.

        Equivalent to ``send(data, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if the send buffer is full.
        """
        return self.send(data, block=False)

    def recv_msg_nowait(self) -> Message:
        """Receive a :class:`Message` on the socket without blocking.

        Equivalent to ``recv_msg(block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv_msg(block=False)

    def send_msg_nowait(self, msg: Message) -> None:
        """Send a :class:`Message` on the socket without blocking.

        Equivalent to ``send_msg(msg, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if the send buffer is full.
        """
        return self.send_msg(msg, block=False)

    def recv_into_nowait(self, buffer: WritableBuffer) -> int:
        """Receive data directly into the provided writable buffer without blocking.

        Equivalent to ``recv_into(buffer, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv_into(buffer, block=False)

    def send_msg(self, msg: Message, block: bool = True) -> None:
        """Send the :class:`Message` ``msg`` on the socket."""
        _lib = self._lib
        base_lib = cast(_BaseLibProtocol, _lib)
        from .exceptions import check_err

        flags = 0
        if not block:
            flags |= base_lib.NNG_FLAG_NONBLOCK
        with msg._mem_freed_lock:
            msg._ensure_can_send()
            # Give up ownership before the call: a KeyboardInterrupt raised as
            # nng_sendmsg returns must not leave the Message owning a msg that
            # nng consumed. If it lands after a failed send, the msg leaks.
            msg._mem_freed = True
            err = base_lib.nng_sendmsg(self.socket, msg._nng_msg, flags)
            if err != 0:
                msg._mem_freed = False
                check_err(err, lib=_lib, ffi=self._ffi)

    _MAX_POOL_SIZE = 32

    def _acquire_recv_helper(self) -> _aio.AIOHelper:
        pool = self._recv_pool
        while pool:
            helper = pool.pop()
            if helper.is_valid_for_current_loop():
                return helper
            helper._free()
        return _aio.AIOHelper(self, self._async_backend)

    def _release_recv_helper(self, helper: _aio.AIOHelper) -> None:
        if (
            not self._socket_closed
            and len(self._recv_pool) < self._MAX_POOL_SIZE
            and helper.is_valid_for_current_loop()
        ):
            self._recv_pool.append(helper)
        else:
            helper._free()

    def _acquire_send_helper(self) -> _aio.AIOHelper:
        pool = self._send_pool
        while pool:
            helper = pool.pop()
            if helper.is_valid_for_current_loop():
                return helper
            helper._free()
        return _aio.AIOHelper(self, self._async_backend)

    def _release_send_helper(self, helper: _aio.AIOHelper) -> None:
        if (
            not self._socket_closed
            and len(self._send_pool) < self._MAX_POOL_SIZE
            and helper.is_valid_for_current_loop()
        ):
            self._send_pool.append(helper)
        else:
            helper._free()

    async def asend_msg(self, msg: Message) -> None:
        """
        Asynchronously send the :class:`Message` ``msg`` on the socket.

        """
        with msg._mem_freed_lock:
            msg._ensure_can_send()
            helper = self._acquire_send_helper()
            try:
                return await helper.asend_msg(msg)
            finally:
                self._release_send_helper(helper)

    async def arecv_msg(self) -> Message:
        """
        Asynchronously receive the :class:`Message` ``msg`` on the socket.
        """
        _check_fork()
        helper = self._acquire_recv_helper()
        try:
            msg = await helper.arecv_msg()
            self._try_associate_msg_with_pipe(msg)
            return msg
        finally:
            self._release_recv_helper(helper)

    def __enter__(self: _SocketSelfT) -> _SocketSelfT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    async def __aenter__(self: _SocketSelfT) -> _SocketSelfT:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the socket. Delegates to synchronous close() since the
        underlying NNG close operation is non-blocking."""
        self.close()

    def __aiter__(self: _SocketSelfT) -> _SocketSelfT:
        return self

    async def __anext__(self) -> bytes:
        import pynng

        try:
            return await self.arecv()
        except pynng.Closed:
            raise StopAsyncIteration

    async def aclose(self) -> None:
        """Asynchronous close. Delegates to the synchronous :meth:`close`
        since the underlying NNG close operation is non-blocking."""
        self.close()

    @property
    def dialers(self) -> tuple[Dialer, ...]:
        """A list of the active dialers"""
        return tuple(self._dialers.values())

    @property
    def listeners(self) -> tuple[Listener, ...]:
        """A list of the active listeners"""
        return tuple(self._listeners.values())

    # Only pipes removed before their ADD_POST was seen are recorded, and any
    # late ADD event for them is already in flight on the dialer or listener
    # thread, so a small bound keeps memory flat without forgetting an id that
    # is still needed.
    _MAX_REMOVED_PIPE_IDS = 1024

    @property
    def pipes(self) -> tuple[Pipe, ...]:
        """A list of the active pipes"""
        with self._pipe_notify_lock:
            return tuple(self._pipes.values())

    def _remember_removed_pipe_id(self, pipe_id: int) -> None:
        # Must be called with self._pipe_notify_lock held.
        ids = self._removed_pipe_ids
        ids[pipe_id] = None
        if len(ids) > self._MAX_REMOVED_PIPE_IDS:
            del ids[next(iter(ids))]

    # Subclasses can override these to return version-specific classes.
    _context_class: type[Context] | None = None
    _pipe_class: type[Pipe] | None = None
    _message_class: type[Message] | None = None
    _dialer_class: type[Dialer] | None = None
    _listener_class: type[Listener] | None = None
    _pipe_event_class: type[PipeEvent[Pipe]] | None = None
    _pipe_event_stream_class: type[PipeEventStream[Pipe]] | None = None

    def new_context(self) -> Context:
        """Return a new :class:`Context` for this socket."""
        ctx_cls = self._context_class or Context
        return ctx_cls(self)

    def add_pre_pipe_connect_cb(self, callback: Callable[[Pipe], object]) -> None:
        """
        Add a callback which will be called before a Pipe is connected to a
        Socket.  You can add as many callbacks as you want, and they will be
        called in the order they were added.

        The callback provided must accept a single argument: a Pipe.  The
        socket associated with the pipe can be accessed through the pipe's
        ``socket`` attribute.  If the pipe is closed, the callbacks for
        post_pipe_connect and post_pipe_remove will not be called.

        """
        with self._pipe_notify_lock:
            self._on_pre_pipe_add.append(callback)

    def add_post_pipe_connect_cb(self, callback: Callable[[Pipe], object]) -> None:
        """
        Add a callback which will be called after a Pipe is connected to a
        Socket.  You can add as many callbacks as you want, and they will be
        called in the order they were added.

        The callback provided must accept a single argument: a :class:`Pipe`.

        """
        with self._pipe_notify_lock:
            self._on_post_pipe_add.append(callback)

    def add_post_pipe_remove_cb(self, callback: Callable[[Pipe], object]) -> None:
        """
        Add a callback which will be called after a Pipe is removed from a
        Socket.  You can add as many callbacks as you want, and they will be
        called in the order they were added.

        The callback provided must accept a single argument: a :class:`Pipe`.

        """
        with self._pipe_notify_lock:
            self._on_post_pipe_remove.append(callback)

    def remove_pre_pipe_connect_cb(self, callback: Callable[[Pipe], object]) -> None:
        """Remove ``callback`` from the list of callbacks for pre pipe connect
        events

        """
        with self._pipe_notify_lock:
            self._on_pre_pipe_add.remove(callback)

    def remove_post_pipe_connect_cb(self, callback: Callable[[Pipe], object]) -> None:
        """Remove ``callback`` from the list of callbacks for post pipe connect
        events

        """
        with self._pipe_notify_lock:
            self._on_post_pipe_add.remove(callback)

    def remove_post_pipe_remove_cb(self, callback: Callable[[Pipe], object]) -> None:
        """Remove ``callback`` from the list of callbacks for post pipe remove
        events

        """
        with self._pipe_notify_lock:
            self._on_post_pipe_remove.remove(callback)

    def pipe_events(self) -> PipeEventStream[Pipe]:
        """Return an async iterator of :class:`PipeEvent` objects.

        Each event has a ``pipe`` attribute (the :class:`Pipe`) and an
        ``event_type`` attribute (one of ``"pre_add"``, ``"post_add"``, or
        ``"remove"``).

        Example::

            async for event in socket.pipe_events():
                print(f"Pipe {event.pipe} {event.event_type}")

        The returned :class:`PipeEventStream` can also be used as an async
        context manager::

            async with socket.pipe_events() as events:
                async for event in events:
                    ...

        Call ``close()`` on the stream (or exit the ``async with`` block) to
        stop receiving events and unregister the internal callbacks.
        """
        stream_cls = self._pipe_event_stream_class or PipeEventStream
        return stream_cls(self)

    def _try_associate_msg_with_pipe(self, msg: Message) -> None:
        """Looks up the nng_msg associated with the ``msg`` and attempts to
        set it on the Message ``msg``

        """
        base_lib = cast(_BaseLibProtocol, self._lib)

        with self._pipe_notify_lock:
            lib_pipe = base_lib.nng_msg_get_pipe(msg._nng_msg)
            pipe_id = int(base_lib.nng_pipe_id(lib_pipe))
            state = self._pipe_states.get(pipe_id)
            if state is not None:
                msg.pipe = state.pipe
            elif pipe_id >= 0:
                # The pipe is already removed; do not put it back in self._pipes.
                pipe_cls = self._pipe_class or Pipe
                msg.pipe = pipe_cls(lib_pipe, self)


def _resolve_socket(
    obj: Socket | _NngSocket | cffi.FFI.CData,
    default_lib: _NngLib,
    default_ffi: cffi.FFI,
) -> tuple[_NngLib, cffi.FFI, _NngSocket]:
    """Return ``(lib, ffi, nng_socket)`` for a :class:`Socket` or an ``nng_socket``.

    A bare ``nng_socket`` carries no library reference, so it is taken to belong
    to ``default_lib``; its cffi type tells whether it really does.
    """
    if isinstance(obj, Socket):
        return obj._lib, obj._ffi, obj.socket
    if default_ffi.typeof(cast("cffi.FFI.CData", obj)) is not default_ffi.typeof(
        "nng_socket"
    ):
        raise ValueError(
            "Cannot use an nng_socket from a different nng version here; "
            "pass the pynng Socket object instead"
        )
    return default_lib, default_ffi, cast("_NngSocket", obj)


def _start_device(
    owners: Iterable[Socket],
    lib: _NngLib,
    aio: _NngAio,
    sock1: _NngSocket,
    sock2: _NngSocket,
) -> None:
    """Start ``nng_device_aio`` and let each Socket in ``owners`` end it on close."""
    base_lib = cast(_BaseLibProtocol, lib)
    with _device_section():
        for owner in owners:
            if owner._socket_closed:
                raise Closed("Object closed", base_lib.NNG_ECLOSED)
        base_lib.nng_device_aio(aio, sock1, sock2)
        for owner in owners:
            owner._device_aios.add(aio)


def _stop_device(owners: Iterable[Socket], aio: _NngAio) -> None:
    """Forget a device aio; call this when it is done and before it is freed."""
    with _device_section():
        for owner in owners:
            owner._device_aios.discard(aio)


def _device_sockets(
    s1: Socket | _NngSocket | cffi.FFI.CData,
    s2: Socket | _NngSocket | cffi.FFI.CData | None,
    default_lib: _NngLib,
    default_ffi: cffi.FFI,
) -> tuple[_NngLib, cffi.FFI, _NngSocket, _NngSocket]:
    """Resolve the two sockets of a device to ``(lib, ffi, sock1, sock2)``."""
    lib1, ffi1, sock1 = _resolve_socket(s1, default_lib, default_ffi)
    if s2 is None:
        null_sock = cast("_NngSocket", ffi1.new("nng_socket *", {"id": 0})[0])
        return lib1, ffi1, sock1, null_sock
    lib2, _, sock2 = _resolve_socket(s2, lib1, ffi1)
    if lib2 is not lib1:
        raise ValueError("Cannot bridge sockets from different nng versions")
    return lib1, ffi1, sock1, sock2


class Dialer:
    """Base class for NNG dialers."""

    def __init__(self, dialer: cffi.FFI.CData, socket: Socket) -> None:
        """
        Args:
            dialer: the initialized `lib.nng_dialer`.
            socket: The Socket associated with the dialer

        """
        self._dialer = dialer
        self.socket = socket

    @property
    def _lib(self) -> _NngLib:
        return self.socket._lib

    @property
    def _ffi(self) -> cffi.FFI:
        return self.socket._ffi

    @property
    def dialer(self) -> _NngDialer:
        return cast("_NngDialer", self._dialer[0])

    def close(self) -> None:
        """
        Close the dialer.
        """
        cast(_BaseLibProtocol, self._lib).nng_dialer_close(self.dialer)
        self.socket._dialers.pop(self.id, None)

    @property
    def id(self) -> int:
        return int(cast(_BaseLibProtocol, self._lib).nng_dialer_id(self.dialer))

    def __enter__(self: _DialerSelfT) -> _DialerSelfT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    async def __aenter__(self: _DialerSelfT) -> _DialerSelfT:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    async def aclose(self) -> None:
        """Asynchronous close. Delegates to the synchronous :meth:`close`
        since the underlying NNG close operation is non-blocking."""
        self.close()


class Listener:
    """Base class for NNG listeners."""

    def __init__(self, listener: cffi.FFI.CData, socket: Socket) -> None:
        """
        Args:
            listener: the initialized `lib.nng_listener`.
            socket: The Socket associated with the listener

        """
        self._listener = listener
        self.socket = socket

    @property
    def _lib(self) -> _NngLib:
        return self.socket._lib

    @property
    def _ffi(self) -> cffi.FFI:
        return self.socket._ffi

    @property
    def listener(self) -> _NngListener:
        return cast("_NngListener", self._listener[0])

    def close(self) -> None:
        """
        Close the listener.
        """
        cast(_BaseLibProtocol, self._lib).nng_listener_close(self.listener)
        self.socket._listeners.pop(self.id, None)

    @property
    def id(self) -> int:
        return int(cast(_BaseLibProtocol, self._lib).nng_listener_id(self.listener))

    def __enter__(self: _ListenerSelfT) -> _ListenerSelfT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    async def __aenter__(self: _ListenerSelfT) -> _ListenerSelfT:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    async def aclose(self) -> None:
        """Asynchronous close. Delegates to the synchronous :meth:`close`
        since the underlying NNG close operation is non-blocking."""
        self.close()


class Pipe:
    """Base class for NNG pipes."""

    tcp_nodelay = ReadOnlyBooleanOption("tcp-nodelay")
    tcp_keepalive = ReadOnlyBooleanOption("tcp-keepalive")

    def __init__(self, lib_pipe: _NngPipe, socket: Socket) -> None:
        _ffi = socket._ffi
        self._pipe = _ffi.new("nng_pipe *")
        self._pipe[0] = lib_pipe
        self._pipe_val: _NngPipe = cast("_NngPipe", self._pipe[0])
        self.socket = socket
        self._closed = False

    @property
    def pipe(self) -> _NngPipe:
        return self._pipe_val

    @property
    def _lib(self) -> _NngLib:
        return self.socket._lib

    @property
    def _ffi(self) -> cffi.FFI:
        return self.socket._ffi

    @property
    def closed(self) -> bool:
        """
        Return whether the pipe has been closed directly.

        This will not be valid if the pipe was closed indirectly, e.g. by
        closing the associated listener/dialer/socket.

        """
        return self._closed

    @property
    def id(self) -> int:
        return int(cast(_BaseLibProtocol, self._lib).nng_pipe_id(self.pipe))

    @property
    def dialer(self) -> Dialer:
        """
        Return the dialer this pipe is associated with.  If the pipe is not
        associated with a dialer, raise an exception

        """
        base_lib = cast(_BaseLibProtocol, self._lib)
        dialer = base_lib.nng_pipe_dialer(self.pipe)
        d_id = int(base_lib.nng_dialer_id(dialer))
        if d_id < 0:
            raise TypeError("This pipe has no associated dialers.")
        return self.socket._dialers[d_id]

    @property
    def listener(self) -> Listener:
        """
        Return the listener this pipe is associated with.  If the pipe is not
        associated with a listener, raise an exception

        """
        base_lib = cast(_BaseLibProtocol, self._lib)
        listener = base_lib.nng_pipe_listener(self.pipe)
        l_id = int(base_lib.nng_listener_id(listener))
        if l_id < 0:
            raise TypeError("This pipe has no associated listeners.")
        return self.socket._listeners[l_id]

    def close(self) -> None:
        """
        Close the pipe.

        """
        from .exceptions import check_err

        check_err(cast(_BaseLibProtocol, self._lib).nng_pipe_close(self.pipe))
        self._closed = True

    def send(self, data: ReadableBuffer) -> None:
        """
        Synchronously send bytes from this :class:`Pipe`.  This method
        automatically creates a :class:`Message`, associates with this pipe,
        and sends it with this pipe's associated :class:`Socket`.

        """
        _ensure_can_send(data)
        msg_cls = self.socket._message_class or Message
        msg = msg_cls(data, self, _lib=self._lib, _ffi=self._ffi)
        self.socket.send_msg(msg)

    def send_msg(self, msg: Message) -> None:
        """
        Synchronously send a Message from this :class:`Pipe`.

        """
        msg.pipe = self
        self.socket.send_msg(msg)

    async def asend(self, data: ReadableBuffer) -> None:
        """
        Asynchronously send bytes from this :class:`Pipe`.

        """
        _ensure_can_send(data)
        msg_cls = self.socket._message_class or Message
        msg = msg_cls(data, self, _lib=self._lib, _ffi=self._ffi)
        return await self.socket.asend_msg(msg)

    async def asend_msg(self, msg: Message) -> None:
        """
        Asynchronously send a Message from this :class:`Pipe`.

        """
        msg.pipe = self
        return await self.socket.asend_msg(msg)


class Context:
    """Base class for NNG contexts."""

    recv_timeout = MsOption("recv-timeout")
    send_timeout = MsOption("send-timeout")

    def __init__(self, socket: Socket) -> None:
        _check_fork()
        _mark_nng_initialized()
        # need to set attributes first, so that if anything goes wrong,
        # __del__() doesn't throw an AttributeError
        self._context: cffi.FFI.CData | None = None
        assert isinstance(socket, Socket)
        self._socket = socket
        _ffi = socket._ffi
        base_lib = cast(_BaseLibProtocol, socket._lib)
        from .exceptions import check_err

        self._context = _ffi.new("nng_ctx *")
        check_err(base_lib.nng_ctx_open(self._context, socket.socket))
        self._recv_pool: list[_aio.AIOHelper] = []
        self._send_pool: list[_aio.AIOHelper] = []

        assert base_lib.nng_ctx_id(self.context) != -1

    @property
    def _lib(self) -> _NngLib:
        return self._socket._lib

    @property
    def _ffi(self) -> cffi.FFI:
        return self._socket._ffi

    _MAX_POOL_SIZE = 32

    def _acquire_recv_helper(self) -> _aio.AIOHelper:
        pool = self._recv_pool
        while pool:
            helper = pool.pop()
            if helper.is_valid_for_current_loop():
                return helper
            helper._free()
        return _aio.AIOHelper(self, self._socket._async_backend)

    def _release_recv_helper(self, helper: _aio.AIOHelper) -> None:
        if (
            self._context is not None
            and len(self._recv_pool) < self._MAX_POOL_SIZE
            and helper.is_valid_for_current_loop()
        ):
            self._recv_pool.append(helper)
        else:
            helper._free()

    def _acquire_send_helper(self) -> _aio.AIOHelper:
        pool = self._send_pool
        while pool:
            helper = pool.pop()
            if helper.is_valid_for_current_loop():
                return helper
            helper._free()
        return _aio.AIOHelper(self, self._socket._async_backend)

    def _release_send_helper(self, helper: _aio.AIOHelper) -> None:
        if (
            self._context is not None
            and len(self._send_pool) < self._MAX_POOL_SIZE
            and helper.is_valid_for_current_loop()
        ):
            self._send_pool.append(helper)
        else:
            helper._free()

    async def arecv(self) -> bytes:
        """Asynchronously receive data using this context."""
        msg = await self.arecv_msg()
        return msg.bytes

    async def asend(self, data: ReadableBuffer) -> None:
        """Asynchronously send data using this context."""
        _ensure_can_send(data)
        helper = self._acquire_send_helper()
        try:
            return await helper.asend(data)
        finally:
            self._release_send_helper(helper)

    def recv_msg(self, block: bool = True) -> Message:
        """Synchronously receive a :class:`Message` using this context."""
        _check_fork()
        _ffi = self._ffi
        _lib = self._lib
        base_lib = cast(_BaseLibProtocol, _lib)
        from .exceptions import Timeout, TryAgain

        if not block:
            timeout = 0
        else:
            timeout = self.recv_timeout

        try:
            nng_msg = _sliced_aio_recv(
                base_lib.nng_ctx_recv,
                self.context,
                _lib,
                _ffi,
                timeout,
                nonblock_recv_fn=(
                    base_lib.nng_ctx_recvmsg
                    if self._socket._nonblock_recv_first
                    else None
                ),
            )
        except Timeout:
            if not block:
                raise TryAgain(
                    "No message available immediately on context",
                    base_lib.NNG_EAGAIN,
                )
            raise
        msg_cls = self._socket._message_class or Message
        msg = msg_cls(nng_msg, _lib=_lib, _ffi=_ffi)
        self._socket._try_associate_msg_with_pipe(msg)
        return msg

    def recv(self, block: bool = True) -> bytes:
        """Synchronously receive data on this context."""
        msg = self.recv_msg(block=block)
        return msg.bytes

    def recv_into(self, buffer: WritableBuffer, block: bool = True) -> int:
        """Receive data directly into the provided writable buffer."""
        m = memoryview(buffer)
        if m.readonly:
            raise BufferError("buffer must be writable")
        msg = self.recv_msg(block=block)
        base_lib = cast(_BaseLibProtocol, self._lib)
        with msg._mem_freed_lock:
            body = base_lib.nng_msg_body(msg._nng_msg)
            msg_len = int(base_lib.nng_msg_len(msg._nng_msg))
            nbytes = min(len(m), msg_len)
            c_buf = self._ffi.from_buffer(m)
            self._ffi.memmove(c_buf, body, nbytes)
        return nbytes

    def recv_nowait(self) -> bytes:
        """Receive data using this context without blocking.

        Equivalent to ``recv(block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv(block=False)

    def send_nowait(self, data: ReadableBuffer) -> None:
        """Send data using this context without blocking.

        Equivalent to ``send(data, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if the send buffer is full.
        """
        return self.send(data, block=False)

    def recv_msg_nowait(self) -> Message:
        """Receive a :class:`Message` using this context without blocking.

        Equivalent to ``recv_msg(block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv_msg(block=False)

    def send_msg_nowait(self, msg: Message) -> None:
        """Send a :class:`Message` using this context without blocking.

        Equivalent to ``send_msg(msg, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if the send buffer is full.
        """
        return self.send_msg(msg, block=False)

    def recv_into_nowait(self, buffer: WritableBuffer) -> int:
        """Receive data directly into buffer using this context without blocking.

        Equivalent to ``recv_into(buffer, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv_into(buffer, block=False)

    async def arecv_into(self, buffer: WritableBuffer) -> int:
        """Asynchronously receive data directly into the provided writable buffer."""
        m = memoryview(buffer)
        if m.readonly:
            raise BufferError("buffer must be writable")
        msg = await self.arecv_msg()
        base_lib = cast(_BaseLibProtocol, self._lib)
        with msg._mem_freed_lock:
            body = base_lib.nng_msg_body(msg._nng_msg)
            msg_len = int(base_lib.nng_msg_len(msg._nng_msg))
            nbytes = min(len(m), msg_len)
            c_buf = self._ffi.from_buffer(m)
            self._ffi.memmove(c_buf, body, nbytes)
        return nbytes

    def send_msg(self, msg: Message, block: bool = True) -> None:
        """Synchronously send the :class:`Message` ``msg`` on the context."""
        _ffi = self._ffi
        _lib = self._lib
        base_lib = cast(_BaseLibProtocol, _lib)
        from .exceptions import TryAgain, check_err

        with msg._mem_freed_lock:
            msg._ensure_can_send()
            aio_p = _ffi.new("nng_aio **")
            check_err(
                base_lib.nng_aio_alloc(aio_p, _ffi.NULL, _ffi.NULL),
                lib=_lib,
                ffi=_ffi,
            )
            aio = cast("_NngAio", aio_p[0])
            # The aio, not a Python flag, records who owns the msg: nng clears
            # the aio's msg when it consumes it. Ownership is given up first
            # and taken back in finally, so an exception at any point (such as
            # KeyboardInterrupt) can at worst leak the msg, never free it twice.
            msg._mem_freed = True
            send_started = False
            try:
                base_lib.nng_aio_set_msg(aio, msg._nng_msg)
                if not block:
                    base_lib.nng_aio_set_timeout(aio, 0)
                send_started = True
                base_lib.nng_ctx_send(self.context, aio)
                base_lib.nng_aio_wait(aio)
                res = base_lib.nng_aio_result(aio)
                if res != 0:
                    if not block and res == base_lib.NNG_ETIMEDOUT:
                        raise TryAgain("Context send buffer full", base_lib.NNG_EAGAIN)
                    check_err(res, lib=_lib, ffi=_ffi)
            finally:
                if send_started:
                    base_lib.nng_aio_cancel(aio)
                    base_lib.nng_aio_wait(aio)
                if cast("cffi.FFI.CData", base_lib.nng_aio_get_msg(aio)) != _ffi.NULL:
                    base_lib.nng_aio_set_msg(aio, _ffi.NULL)
                    msg._mem_freed = False
                base_lib.nng_aio_free(aio)

    def send(self, data: ReadableBuffer, block: bool = True) -> None:
        """
        Synchronously send data on the context.

        """
        _ensure_can_send(data)
        msg_cls = self._socket._message_class or Message
        msg = msg_cls(data, _lib=self._lib, _ffi=self._ffi)
        return self.send_msg(msg, block=block)

    def close(self) -> None:
        """Close this context."""
        base_lib = cast(_BaseLibProtocol, self._lib)
        from .exceptions import check_err

        ctx_err = 0
        while self._recv_pool:
            self._recv_pool.pop()._free()
        while self._send_pool:
            self._send_pool.pop()._free()
        if self._context is not None:
            # check that nng still has a reference
            if base_lib.nng_ctx_id(self.context) != -1:
                ctx_err = base_lib.nng_ctx_close(self.context)
                self._context = None
                check_err(ctx_err)

    def __enter__(self: _ContextSelfT) -> _ContextSelfT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    async def __aenter__(self: _ContextSelfT) -> _ContextSelfT:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the context. Delegates to synchronous close() since the
        underlying NNG close operation is non-blocking."""
        self.close()

    def __aiter__(self: _ContextSelfT) -> _ContextSelfT:
        return self

    async def __anext__(self) -> bytes:
        import pynng

        try:
            return await self.arecv()
        except pynng.Closed:
            raise StopAsyncIteration

    async def aclose(self) -> None:
        """Asynchronous close. Delegates to the synchronous :meth:`close`
        since the underlying NNG close operation is non-blocking."""
        self.close()

    @property
    def context(self) -> _NngCtx:
        """Return the underlying nng object."""
        assert self._context is not None
        return cast("_NngCtx", self._context[0])

    def __del__(self) -> None:
        if _is_nng_finalized():
            return
        try:
            self.close()
        except (TypeError, AttributeError, NNGException):
            pass

    async def asend_msg(self, msg: Message) -> None:
        """
        Asynchronously send the :class:`Message` ``msg`` on the context.
        """
        with msg._mem_freed_lock:
            msg._ensure_can_send()
            helper = self._acquire_send_helper()
            try:
                return await helper.asend_msg(msg)
            finally:
                self._release_send_helper(helper)

    async def arecv_msg(self) -> Message:
        """
        Asynchronously receive a :class:`Message` on the context.
        """
        _check_fork()
        helper = self._acquire_recv_helper()
        try:
            msg = await helper.arecv_msg()
            self._socket._try_associate_msg_with_pipe(msg)
            return msg
        finally:
            self._release_recv_helper(helper)


if TYPE_CHECKING:
    _OptionTarget: TypeAlias = Socket | Dialer | Listener | Pipe | Context


class Message:
    """Base class for NNG messages.

    Accepts optional ``_lib`` and ``_ffi`` keyword arguments to specify
    which CFFI bindings to use. If not provided, falls back to v1 defaults.
    """

    __slots__ = (
        "__lib",
        "__ffi",
        "_mem_freed",
        "_mem_freed_lock",
        "_nng_msg",
        "_pipe",
    )

    def __init__(
        self,
        data: ReadableBuffer | _NngMsg | cffi.FFI.CData,
        pipe: Pipe | None = None,
        *,
        _lib: _NngLib | None = None,
        _ffi: cffi.FFI | None = None,
    ) -> None:
        # Resolve lib/ffi: explicit args > pipe's socket > v1 default
        if _lib is None or _ffi is None:
            if pipe is not None and hasattr(pipe, "socket"):
                if _lib is None:
                    _lib = pipe.socket._lib
                if _ffi is None:
                    _ffi = pipe.socket._ffi
            else:
                if _lib is None:
                    from ._nng import lib

                    _lib = lib
                if _ffi is None:
                    from ._nng import ffi

                    _ffi = ffi

        assert _lib is not None
        assert _ffi is not None
        self.__lib: _NngLib = _lib
        self.__ffi: cffi.FFI = _ffi
        self._mem_freed = False
        self._mem_freed_lock = threading.Lock()
        self._nng_msg: _NngMsg
        self._pipe: Pipe | None = None

        from .exceptions import check_err

        base_lib = cast(_BaseLibProtocol, _lib)
        if (
            isinstance(data, _ffi.CData)
            and _ffi.typeof(data).cname == "struct nng_msg *"
        ):
            self._nng_msg = cast("_NngMsg", data)
        else:
            _ensure_can_send(data)
            buf_data = cast(ReadableBuffer, data)
            m = memoryview(buf_data)
            c_buf: bytes | cffi.FFI.CData
            if isinstance(buf_data, bytes):
                c_buf = buf_data
            else:
                c_buf = _ffi.from_buffer(m)
            msg_p = _ffi.new("nng_msg **")
            check_err(base_lib.nng_msg_alloc(msg_p, 0))
            msg = cast("_NngMsg", msg_p[0])
            try:
                check_err(base_lib.nng_msg_append(msg, c_buf, len(m)))
            except Exception:
                base_lib.nng_msg_free(msg)
                raise
            self._nng_msg = msg

        if pipe is None:
            self._pipe = None
        else:
            self.pipe = pipe

    @property
    def _lib(self) -> _NngLib:
        return self.__lib

    @property
    def _ffi(self) -> cffi.FFI:
        return self.__ffi

    @property
    def pipe(self) -> Pipe | None:
        return self._pipe

    @pipe.setter
    def pipe(self, pipe: Pipe) -> None:
        if not isinstance(pipe, Pipe):
            msg = f"pipe must be type Pipe, not {type(pipe)}"
            raise ValueError(msg)
        from .exceptions import check_err

        check_err(
            cast(_BaseLibProtocol, self.__lib).nng_msg_set_pipe(
                self._nng_msg, pipe.pipe
            )
        )
        self._pipe = pipe

    @property
    def _buffer(self) -> cffi.FFI.buffer:
        """
        Returns a cffi.buffer to the underlying nng_msg buffer.

        If you access the message's buffer using this property, you must ensure
        that you do not send the message until you are not using the buffer
        anymore.

        """
        import pynng

        base_lib = cast(_BaseLibProtocol, self.__lib)
        _ffi = self.__ffi
        with self._mem_freed_lock:
            if self._mem_freed:
                raise pynng.MessageStateError(
                    "Message buffer is no longer available after sending."
                )
            size = base_lib.nng_msg_len(self._nng_msg)
            data = _ffi.cast("char *", base_lib.nng_msg_body(self._nng_msg))
            return _ffi.buffer(data[0:size])

    @property
    def header(self) -> bytes:
        """Return the bytes from the message header."""
        import pynng

        base_lib = cast(_BaseLibProtocol, self.__lib)
        _ffi = self.__ffi
        with self._mem_freed_lock:
            if self._mem_freed:
                raise pynng.MessageStateError(
                    "Message header is no longer available after sending."
                )
            size = base_lib.nng_msg_header_len(self._nng_msg)
            if size == 0:
                return b""
            data = _ffi.cast("char *", base_lib.nng_msg_header(self._nng_msg))
            return bytes(_ffi.buffer(data[0:size]))

    def header_append(self, data: ReadableBuffer) -> None:
        """Append data to the message header.

        Args:
            data: Any buffer-protocol object (e.g. bytes, bytearray, memoryview).
        """
        base_lib = cast(_BaseLibProtocol, self.__lib)
        _ffi = self.__ffi
        from .exceptions import check_err

        with self._mem_freed_lock:
            self._ensure_can_send()
            m = memoryview(data)
            c_buf: bytes | cffi.FFI.CData
            if isinstance(data, bytes):
                c_buf = data
            else:
                c_buf = _ffi.from_buffer(m)
            check_err(base_lib.nng_msg_header_append(self._nng_msg, c_buf, len(m)))

    @property
    def bytes(self) -> bytes:
        """
        Return the bytes from the underlying buffer.

        """
        return bytes(self._buffer)

    def header_trim(self, sz: int) -> None:
        """Trim sz bytes from the start of the message header."""
        base_lib = cast(_BaseLibProtocol, self.__lib)
        from .exceptions import check_err

        with self._mem_freed_lock:
            self._ensure_can_send()
            check_err(base_lib.nng_msg_header_trim(self._nng_msg, sz))

    def header_chop(self, sz: int) -> None:
        """Chop sz bytes from the end of the message header."""
        base_lib = cast(_BaseLibProtocol, self.__lib)
        from .exceptions import check_err

        with self._mem_freed_lock:
            self._ensure_can_send()
            check_err(base_lib.nng_msg_header_chop(self._nng_msg, sz))

    def header_clear(self) -> None:
        """Clear all data from the message header."""
        base_lib = cast(_BaseLibProtocol, self.__lib)
        with self._mem_freed_lock:
            self._ensure_can_send()
            base_lib.nng_msg_header_clear(self._nng_msg)

    def copy(self: _MessageSelfT) -> _MessageSelfT:
        """Create a duplicate copy of this message."""
        _lib = self.__lib
        _ffi = self.__ffi
        base_lib = cast(_BaseLibProtocol, _lib)
        import pynng
        from .exceptions import check_err

        with self._mem_freed_lock:
            if self._mem_freed:
                raise pynng.MessageStateError(
                    "Cannot copy a message that has already been sent."
                )
            dup_p = _ffi.new("nng_msg **")
            check_err(base_lib.nng_msg_dup(dup_p, self._nng_msg))
            msg_cls = type(self)
            return msg_cls(
                cast("_NngMsg", dup_p[0]),
                pipe=self._pipe,
                _lib=_lib,
                _ffi=_ffi,
            )

    def dup(self: _MessageSelfT) -> _MessageSelfT:
        """Alias for :meth:`copy`."""
        return self.copy()

    def __del__(self) -> None:
        if _is_nng_finalized():
            return
        if not hasattr(self, "_mem_freed_lock"):
            return
        with self._mem_freed_lock:
            if self._mem_freed:
                return
            else:
                if getattr(self, "_nng_msg", None) is not None:
                    cast(_BaseLibProtocol, self.__lib).nng_msg_free(self._nng_msg)
                self._mem_freed = True

    def _ensure_can_send(self) -> None:
        """
        Raises an exception if the message's state is such that it cannot be
        sent.  The _mem_freed_lock() must be acquired when this method is
        called.

        """
        _check_fork()
        import pynng

        assert self._mem_freed_lock.locked()
        if self._mem_freed:
            msg = "Attempted to send the same message more than once."
            raise pynng.MessageStateError(msg)
