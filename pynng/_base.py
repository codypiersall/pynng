"""
Version-independent base classes for pynng.

This module contains the shared base classes that both v1 and v2 protocol
implementations inherit from. All classes use instance-level ``_lib`` and
``_ffi`` attributes instead of module-level globals, enabling the same
code to work with either nng v1 or v2 CFFI bindings.

This is an internal module. Users should import from ``pynng`` (v1) or
``pynng.v2`` (v2).
"""

import asyncio
import collections
import logging
import math
import os
import threading
import time
import weakref

import sniffio

from . import options
from . import _aio
from .exceptions import NNGException
from ._finalized import is_nng_finalized as _is_nng_finalized

logger = logging.getLogger(__name__)

# Keep track of initialized PID to intercept and prevent unsupported fork() calls.
_init_pid = None
_is_forked_child = False


def _after_fork_in_child():
    global _is_forked_child
    if _init_pid is not None:
        _is_forked_child = True


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_in_child)


def _mark_nng_initialized():
    """Record the PID when NNG is initialized."""
    global _init_pid
    if _init_pid is None:
        _init_pid = os.getpid()


def _check_fork():
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



# Keep CFFI socket handles alive for callbacks until socket close.
_active_handles = {}
_active_handles_lock = threading.Lock()

# Retain closed sockets and pointer options (e.g. TLSConfig) in a FIFO buffer
# so that NNG background reaper threads (tls_reap, listener_reap, dialer_reap)
# finish tearing down C-level mbedTLS structures before Python GC finalizes them.
_RETAIN_CLOSED_MAX = 64
_closed_objects_retained = collections.deque(maxlen=_RETAIN_CLOSED_MAX)
_closed_objects_lock = threading.Lock()


def _retain_closed(obj):
    if obj is not None:
        with _closed_objects_lock:
            _closed_objects_retained.append(obj)


PipeEvent = collections.namedtuple("PipeEvent", ["pipe", "event_type"])
"""A pipe event with the pipe and the event type.

Attributes:
    pipe: The :class:`Pipe` associated with the event.
    event_type: One of ``"pre_add"``, ``"post_add"``, or ``"remove"``.
"""


_SENTINEL = object()
_RECV_SLICE_MS = 100  # Slice duration for interruptable recv loop (ms)


def _sliced_aio_recv(
    recv_fn, target_handle, lib, ffi, timeout_ms, slice_ms=_RECV_SLICE_MS
):
    """Perform an interruptable receive using nng_aio with sliced timeouts.

    CFFI releases the GIL when blocking in C. If a thread waits in a long or
    infinite C wait (e.g. pthread_cond_wait), Python signal handlers (such as
    KeyboardInterrupt on Ctrl-C) are never triggered until C returns.
    By slicing the wait into short intervals (default 100ms), Python's runtime
    regularly regains the GIL to process pending signals.

    Args:
        recv_fn: C function to initiate receive (e.g. nng_recv_aio, nng_socket_recv, nng_ctx_recv).
        target_handle: CFFI socket or context handle.
        lib: CFFI library instance.
        ffi: CFFI ffi instance.
        timeout_ms: Total timeout in milliseconds (-1 for infinite).
        slice_ms: Slice interval in milliseconds.

    Returns:
        nng_msg*: Pointer to received C message.
    """
    from .exceptions import check_err

    if timeout_ms is not None and timeout_ms >= 0:
        deadline = time.monotonic() + (timeout_ms / 1000.0)
    else:
        deadline = None

    aio_p = ffi.new("nng_aio **")
    check_err(lib.nng_aio_alloc(aio_p, ffi.NULL, ffi.NULL))
    aio = aio_p[0]

    first_attempt = True
    try:
        while True:
            if deadline is None:
                cur_slice = slice_ms
            else:
                now = time.monotonic()
                if not first_attempt and now >= deadline:
                    check_err(lib.NNG_ETIMEDOUT, lib=lib, ffi=ffi)
                remaining_ms = int(math.ceil((deadline - now) * 1000.0))
                cur_slice = max(0, min(remaining_ms, slice_ms))
            first_attempt = False

            t_start = time.monotonic()
            lib.nng_aio_set_timeout(aio, cur_slice)
            recv_fn(target_handle, aio)
            lib.nng_aio_wait(aio)
            err = lib.nng_aio_result(aio)
            elapsed_slice = time.monotonic() - t_start

            if err == lib.NNG_ETIMEDOUT:
                if deadline is not None and time.monotonic() >= deadline:
                    check_err(lib.NNG_ETIMEDOUT, lib=lib, ffi=ffi)
                if cur_slice > 10 and elapsed_slice < (cur_slice * 0.8) / 1000.0:
                    check_err(lib.NNG_ETIMEDOUT, lib=lib, ffi=ffi)
                continue

            check_err(err, lib=lib, ffi=ffi)
            return lib.nng_aio_get_msg(aio)
    except BaseException:
        lib.nng_aio_cancel(aio)
        lib.nng_aio_wait(aio)
        raise
    finally:
        lib.nng_aio_free(aio)


def _ensure_can_send(thing):
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


def to_char(charlike, add_null_term=False, ffi=None):
    """Convert str or bytes to char*.

    Args:
        charlike: The string-like object to convert.
        add_null_term: Whether to add a null terminator.
        ffi: The CFFI ffi instance to use. If None, uses v1's ffi.
    """
    if ffi is None:
        from ._nng import ffi as _ffi

        ffi = _ffi
    # fast path for stuff that doesn't need to be changed.
    if isinstance(charlike, ffi.CData):
        return charlike
    if isinstance(charlike, str):
        charlike = charlike.encode()
    if add_null_term:
        charlike = charlike + b"\x00"
    charlike = ffi.new("char[]", charlike)
    return charlike


def _do_callbacks(pipe, callbacks):
    for cb in callbacks:
        try:
            cb(pipe)
        except Exception:
            msg = "Exception raised in pre pipe connect callback {!r}"
            logger.exception(msg.format(cb))


class PipeEventStream:
    """Async iterator that yields :class:`PipeEvent` objects.

    Returned by :meth:`Socket.pipe_events`.  Use it with ``async for``::

        async for event in socket.pipe_events():
            print(f"Pipe {event.pipe} {event.event_type}")

    Call :meth:`close` or use ``async with`` to stop receiving events and
    unregister the internal callbacks.
    """

    def __init__(self, socket):
        self._socket = socket
        self._closed = False
        backend = socket._async_backend
        if backend is None:
            backend = sniffio.current_async_library()
        self._backend = backend

        if self._backend == "asyncio":
            self._queue = asyncio.Queue()
            self._loop = asyncio.get_running_loop()
        elif self._backend == "trio":
            import trio

            self._send_channel, self._receive_channel = trio.open_memory_channel(
                math.inf
            )
            self._trio_token = trio.lowlevel.current_trio_token()
        else:
            raise ValueError(
                "The async backend {} is not currently supported.".format(backend)
            )

        # Register callbacks
        self._socket.add_pre_pipe_connect_cb(self._on_pre_add)
        self._socket.add_post_pipe_connect_cb(self._on_post_add)
        self._socket.add_post_pipe_remove_cb(self._on_remove)

    def _put_event(self, event):
        """Thread-safe put of an event into the async queue."""
        if self._closed:
            return
        if self._backend == "asyncio":
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        elif self._backend == "trio":
            self._trio_token.run_sync_soon(
                self._trio_send_nowait,
                event,
            )

    def _trio_send_nowait(self, event):
        """Wrapper for send_nowait that suppresses ClosedResourceError.

        Called via ``run_sync_soon`` from a foreign thread, so any exception
        raised here would crash the Trio event loop.
        """
        import trio

        try:
            self._send_channel.send_nowait(event)
        except trio.ClosedResourceError:
            pass

    def _on_pre_add(self, pipe):
        self._put_event(PipeEvent(pipe=pipe, event_type="pre_add"))

    def _on_post_add(self, pipe):
        self._put_event(PipeEvent(pipe=pipe, event_type="post_add"))

    def _on_remove(self, pipe):
        self._put_event(PipeEvent(pipe=pipe, event_type="remove"))

    def close(self):
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

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._closed:
            raise StopAsyncIteration
        if self._backend == "asyncio":
            item = await self._queue.get()
            if item is _SENTINEL:
                raise StopAsyncIteration
            return item
        elif self._backend == "trio":
            import trio

            try:
                return await self._receive_channel.receive()
            except trio.EndOfChannel:
                raise StopAsyncIteration

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self.close()


# --- Option descriptors ---
# These descriptors call into options.py, which resolves lib/ffi from the
# owning instance.


class _NNGOption:
    """A descriptor for more easily getting/setting NNG option."""

    # this class should not be instantiated directly!  Instantiation will work,
    # but getting/setting will fail.

    # subclasses set _getter and _setter to the module-level getter and setter
    # functions
    _getter = None
    _setter = None

    def __init__(self, option_name):
        self.option = to_char(option_name)

    def __get__(self, instance, owner):
        # have to look up the getter on the class
        if self._getter is None:
            raise TypeError("{} is write-only".format(self.__class__))
        return self.__class__._getter(instance, self.option)

    def __set__(self, instance, value):
        if self._setter is None:
            raise TypeError("{} is readonly".format(self.__class__))
        self.__class__._setter(instance, self.option, value)


class IntOption(_NNGOption):
    """Descriptor for getting/setting integer options"""

    _getter = options._getopt_int
    _setter = options._setopt_int


class MsOption(_NNGOption):
    """Descriptor for getting/setting durations (in milliseconds)"""

    _getter = options._getopt_ms
    _setter = options._setopt_ms


class SockAddrOption(_NNGOption):
    """Descriptor for getting/setting durations (in milliseconds)"""

    _getter = options._getopt_sockaddr


class SizeOption(_NNGOption):
    """Descriptor for getting/setting size_t options"""

    _getter = options._getopt_size
    _setter = options._setopt_size


class StringOption(_NNGOption):
    """Descriptor for getting/setting string options"""

    _getter = options._getopt_string
    _setter = options._setopt_string


class BooleanOption(_NNGOption):
    """Descriptor for getting/setting boolean values"""

    _getter = options._getopt_bool
    _setter = options._setopt_bool


class PointerOption(_NNGOption):
    """Descriptor for setting pointer values"""

    _setter = options._setopt_ptr

    def __set__(self, instance, value):
        super().__set__(instance, value)
        if instance is not None and value is not None:
            if not hasattr(instance, "_pointer_option_refs"):
                instance._pointer_option_refs = {}
            instance._pointer_option_refs[self.option] = value
            _retain_closed(value)


class NotImplementedOption(_NNGOption):
    """Represents a currently un-implemented option in Python."""

    def __init__(self, option_name, errmsg):
        super().__init__(option_name)
        self.errmsg = errmsg

    def __get__(self, instance, owner):
        raise NotImplementedError(self.errmsg)

    def __set__(self, instance, value):
        raise NotImplementedError(self.errmsg)


# --- Base classes ---


class Socket:
    """Base socket class. Version-specific subclasses must set _lib and _ffi.

    This should not be instantiated directly; use protocol subclasses from
    ``pynng`` (v1) or ``pynng.v2`` (v2).
    """

    # Subclasses MUST set these to the appropriate CFFI lib and ffi.
    _lib = None
    _ffi = None

    # Version tag for _active_handles keys. Prevents ID collision between
    # v1 and v2 sockets.
    _version_tag = None
    _aio_recv_fn = None
    _aio_send_fn = None
    survey_time = None

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
        dial=None,
        listen=None,
        recv_timeout=None,
        send_timeout=None,
        recv_buffer_size=None,
        send_buffer_size=None,
        recv_max_size=None,
        reconnect_time_min=None,
        reconnect_time_max=None,
        opener=None,
        raw=False,
        block_on_dial=None,
        async_backend=None,
        **kwargs,
    ):
        _check_fork()
        _mark_nng_initialized()

        # mapping of id: Python objects
        self._dialers = {}
        self._listeners = {}
        self._pipes = {}
        self._on_pre_pipe_add = []
        self._on_post_pipe_add = []
        self._on_post_pipe_remove = []
        self._pipe_notify_lock = threading.Lock()
        self._socket_closed = False
        self._close_lock = threading.Lock()
        self._async_backend = async_backend
        self._recv_pool = []
        self._send_pool = []

        _ffi = self._ffi
        _lib = self._lib

        self._socket = _ffi.new(
            "nng_socket *",
        )
        if opener is not None:
            self._opener = opener
        elif raw and hasattr(self, "_raw_opener"):
            self._opener = self._raw_opener
        elif not hasattr(self, "_opener"):
            raise TypeError("Cannot directly instantiate a Socket.  Try a subclass.")
        from .exceptions import check_err

        check_err(self._opener(self._socket))

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

        if listen is not None:
            self.listen(listen)
        if dial is not None:
            self.dial(dial, block=block_on_dial)

    def _setup_pipe_callbacks(self):
        """Register pipe notification callbacks with NNG."""
        _ffi = self._ffi
        _lib = self._lib

        handle = _ffi.new_handle(self)
        self._handle = handle
        version_tag = self._version_tag
        sock_id = _lib.nng_socket_id(self.socket)
        with _active_handles_lock:
            _active_handles[(version_tag, sock_id)] = weakref.ref(self)

        for event in (
            _lib.NNG_PIPE_EV_ADD_PRE,
            _lib.NNG_PIPE_EV_ADD_POST,
            _lib.NNG_PIPE_EV_REM_POST,
        ):
            from .exceptions import check_err

            check_err(
                _lib.nng_pipe_notify(self.socket, event, _lib._nng_pipe_cb, handle)
            )

    def dial(self, address, *, block=None):
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

    def _dial(self, address, flags=0):
        """Dial specified ``address``

        ``flags`` usually do not need to be given.

        """
        _ffi = self._ffi
        _lib = self._lib
        from .exceptions import check_err

        dialer = _ffi.new("nng_dialer *")
        ret = _lib.nng_dial(self.socket, to_char(address, ffi=_ffi), dialer, flags)
        check_err(ret)
        # we can only get here if check_err doesn't raise
        d_id = _lib.nng_dialer_id(dialer[0])
        dialer_cls = self._dialer_class or Dialer
        py_dialer = dialer_cls(dialer, self)
        self._dialers[d_id] = py_dialer
        return py_dialer

    def listen(self, address, flags=0):
        """Listen at specified address.

        ``listener`` and ``flags`` usually do not need to be given.

        """
        _check_fork()
        _ffi = self._ffi
        _lib = self._lib
        from .exceptions import check_err

        listener = _ffi.new("nng_listener *")
        ret = _lib.nng_listen(self.socket, to_char(address, ffi=_ffi), listener, flags)
        check_err(ret)
        # we can only get here if check_err doesn't raise
        l_id = _lib.nng_listener_id(listener[0])
        listener_cls = self._listener_class or Listener
        py_listener = listener_cls(listener, self)
        self._listeners[l_id] = py_listener
        return py_listener

    def _do_close(self, close_fn):
        """Common close pattern used by both v1 and v2.

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
        _lib = self._lib
        version_tag = self._version_tag
        sock_id = _lib.nng_socket_id(self.socket)
        close_fn(self.socket)
        with _active_handles_lock:
            key = (version_tag, sock_id)
            ref = _active_handles.get(key)
            if ref is not None and (ref() is self or ref() is None):
                del _active_handles[key]
        self._listeners = {}
        self._dialers = {}
        while self._recv_pool:
            self._recv_pool.pop()._free()
        while self._send_pool:
            self._send_pool.pop()._free()

    def __del__(self):
        if _is_nng_finalized():
            return
        try:
            self.close()
        except (TypeError, AttributeError):
            pass

    @property
    def socket(self):
        return self._socket[0]

    def recv_msg(self, block=True):
        """Receive a :class:`Message` on the socket."""
        _check_fork()
        _ffi = self._ffi
        _lib = self._lib
        from .exceptions import check_err

        if not block:
            flags = _lib.NNG_FLAG_NONBLOCK
            msg_p = _ffi.new("nng_msg **")
            check_err(_lib.nng_recvmsg(self.socket, msg_p, flags), lib=_lib, ffi=_ffi)
            raw_msg = msg_p[0]
        else:
            if self._aio_recv_fn is not None:
                recv_fn = self._aio_recv_fn
            else:
                recv_fn = _lib.nng_recv_aio
            timeout = self.recv_timeout
            if self.survey_time is not None and self.survey_time >= 0:
                st = self.survey_time
                if timeout is None or timeout < 0:
                    timeout = st
                else:
                    timeout = min(timeout, st)
            raw_msg = _sliced_aio_recv(recv_fn, self.socket, _lib, _ffi, timeout)

        msg_cls = self._message_class or Message
        msg = msg_cls(raw_msg, _lib=_lib, _ffi=_ffi)
        self._try_associate_msg_with_pipe(msg)
        return msg

    def recv_into(self, buffer, block=True):
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
        with msg._mem_freed_lock:
            body = self._lib.nng_msg_body(msg._nng_msg)
            msg_len = self._lib.nng_msg_len(msg._nng_msg)
            nbytes = min(len(m), msg_len)
            c_buf = self._ffi.from_buffer(m)
            self._ffi.memmove(c_buf, body, nbytes)
        return nbytes

    async def arecv_into(self, buffer):
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
        with msg._mem_freed_lock:
            body = self._lib.nng_msg_body(msg._nng_msg)
            msg_len = self._lib.nng_msg_len(msg._nng_msg)
            nbytes = min(len(m), msg_len)
            c_buf = self._ffi.from_buffer(m)
            self._ffi.memmove(c_buf, body, nbytes)
        return nbytes

    def recv_nowait(self):
        """Receive data on the socket without blocking.

        Equivalent to ``recv(block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv(block=False)

    def send_nowait(self, data):
        """Send data on the socket without blocking.

        Equivalent to ``send(data, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if the send buffer is full.
        """
        return self.send(data, block=False)

    def recv_msg_nowait(self):
        """Receive a :class:`Message` on the socket without blocking.

        Equivalent to ``recv_msg(block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv_msg(block=False)

    def send_msg_nowait(self, msg):
        """Send a :class:`Message` on the socket without blocking.

        Equivalent to ``send_msg(msg, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if the send buffer is full.
        """
        return self.send_msg(msg, block=False)

    def recv_into_nowait(self, buffer):
        """Receive data directly into the provided writable buffer without blocking.

        Equivalent to ``recv_into(buffer, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv_into(buffer, block=False)

    def send_msg(self, msg, block=True):
        """Send the :class:`Message` ``msg`` on the socket."""
        _lib = self._lib
        from .exceptions import check_err

        flags = 0
        if not block:
            flags |= _lib.NNG_FLAG_NONBLOCK
        with msg._mem_freed_lock:
            msg._ensure_can_send()
            check_err(
                _lib.nng_sendmsg(self.socket, msg._nng_msg, flags),
                lib=_lib,
                ffi=self._ffi,
            )
            msg._mem_freed = True

    _MAX_POOL_SIZE = 32

    def _acquire_recv_helper(self):
        pool = self._recv_pool
        while pool:
            helper = pool.pop()
            if helper.is_valid_for_current_loop():
                return helper
            helper._free()
        return _aio.AIOHelper(self, self._async_backend)

    def _release_recv_helper(self, helper):
        if (
            not self._socket_closed
            and len(self._recv_pool) < self._MAX_POOL_SIZE
            and helper.is_valid_for_current_loop()
        ):
            self._recv_pool.append(helper)
        else:
            helper._free()

    def _acquire_send_helper(self):
        pool = self._send_pool
        while pool:
            helper = pool.pop()
            if helper.is_valid_for_current_loop():
                return helper
            helper._free()
        return _aio.AIOHelper(self, self._async_backend)

    def _release_send_helper(self, helper):
        if (
            not self._socket_closed
            and len(self._send_pool) < self._MAX_POOL_SIZE
            and helper.is_valid_for_current_loop()
        ):
            self._send_pool.append(helper)
        else:
            helper._free()

    async def asend_msg(self, msg):
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

    async def arecv_msg(self):
        """
        Asynchronously receive the :class:`Message` ``msg`` on the socket.
        """
        helper = self._acquire_recv_helper()
        try:
            msg = await helper.arecv_msg()
            self._try_associate_msg_with_pipe(msg)
            return msg
        finally:
            self._release_recv_helper(helper)

    def __enter__(self):
        return self

    def __exit__(self, *tb_info):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *tb_info):
        """Close the socket. Delegates to synchronous close() since the
        underlying NNG close operation is non-blocking."""
        self.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        import pynng

        try:
            return await self.arecv()
        except pynng.Closed:
            raise StopAsyncIteration

    async def aclose(self):
        """Asynchronous close. Delegates to the synchronous :meth:`close`
        since the underlying NNG close operation is non-blocking."""
        self.close()

    @property
    def dialers(self):
        """A list of the active dialers"""
        return tuple(self._dialers.values())

    @property
    def listeners(self):
        """A list of the active listeners"""
        return tuple(self._listeners.values())

    @property
    def pipes(self):
        """A list of the active pipes"""
        with self._pipe_notify_lock:
            return tuple(self._pipes.values())

    def _add_pipe(self, lib_pipe):
        # this is only called inside the pipe callback.
        _lib = self._lib
        pipe_id = _lib.nng_pipe_id(lib_pipe)

        # If the pipe already exists in the Socket, don't create a new one
        if pipe_id not in self._pipes:
            pipe_cls = self._pipe_class or Pipe
            pipe = pipe_cls(lib_pipe, self)
            self._pipes[pipe_id] = pipe

        return self._pipes[pipe_id]

    def _remove_pipe(self, lib_pipe):
        _lib = self._lib
        pipe_id = _lib.nng_pipe_id(lib_pipe)
        self._pipes.pop(pipe_id, None)

    # Subclasses can override these to return version-specific classes.
    _context_class = None
    _pipe_class = None
    _message_class = None
    _dialer_class = None
    _listener_class = None

    def new_context(self):
        """Return a new :class:`Context` for this socket."""
        ctx_cls = self._context_class or Context
        return ctx_cls(self)

    def add_pre_pipe_connect_cb(self, callback):
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

    def add_post_pipe_connect_cb(self, callback):
        """
        Add a callback which will be called after a Pipe is connected to a
        Socket.  You can add as many callbacks as you want, and they will be
        called in the order they were added.

        The callback provided must accept a single argument: a :class:`Pipe`.

        """
        with self._pipe_notify_lock:
            self._on_post_pipe_add.append(callback)

    def add_post_pipe_remove_cb(self, callback):
        """
        Add a callback which will be called after a Pipe is removed from a
        Socket.  You can add as many callbacks as you want, and they will be
        called in the order they were added.

        The callback provided must accept a single argument: a :class:`Pipe`.

        """
        with self._pipe_notify_lock:
            self._on_post_pipe_remove.append(callback)

    def remove_pre_pipe_connect_cb(self, callback):
        """Remove ``callback`` from the list of callbacks for pre pipe connect
        events

        """
        with self._pipe_notify_lock:
            self._on_pre_pipe_add.remove(callback)

    def remove_post_pipe_connect_cb(self, callback):
        """Remove ``callback`` from the list of callbacks for post pipe connect
        events

        """
        with self._pipe_notify_lock:
            self._on_post_pipe_add.remove(callback)

    def remove_post_pipe_remove_cb(self, callback):
        """Remove ``callback`` from the list of callbacks for post pipe remove
        events

        """
        with self._pipe_notify_lock:
            self._on_post_pipe_remove.remove(callback)

    def pipe_events(self):
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
        return PipeEventStream(self)

    def _try_associate_msg_with_pipe(self, msg):
        """Looks up the nng_msg associated with the ``msg`` and attempts to
        set it on the Message ``msg``

        """
        _lib = self._lib

        with self._pipe_notify_lock:
            lib_pipe = _lib.nng_msg_get_pipe(msg._nng_msg)
            pipe_id = _lib.nng_pipe_id(lib_pipe)
            try:
                msg.pipe = self._pipes[pipe_id]
            except KeyError:
                if pipe_id >= 0:
                    msg.pipe = self._add_pipe(lib_pipe)


class Dialer:
    """Base class for NNG dialers."""

    local_address = SockAddrOption("local-address")
    remote_address = SockAddrOption("remote-address")
    reconnect_time_min = MsOption("reconnect-time-min")
    reconnect_time_max = MsOption("reconnect-time-max")
    recv_max_size = SizeOption("recv-size-max")
    url = StringOption("url")
    peer = IntOption("peer")
    peer_name = StringOption("peer-name")
    tcp_nodelay = BooleanOption("tcp-nodelay")
    tcp_keepalive = BooleanOption("tcp-keepalive")

    def __init__(self, dialer, socket):
        """
        Args:
            dialer: the initialized `lib.nng_dialer`.
            socket: The Socket associated with the dialer

        """
        self._dialer = dialer
        self.socket = socket

    @property
    def _lib(self):
        return self.socket._lib

    @property
    def _ffi(self):
        return self.socket._ffi

    @property
    def dialer(self):
        return self._dialer[0]

    def close(self):
        """
        Close the dialer.
        """
        self._lib.nng_dialer_close(self.dialer)
        self.socket._dialers.pop(self.id, None)

    @property
    def id(self):
        return self._lib.nng_dialer_id(self.dialer)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self.close()

    async def aclose(self):
        """Asynchronous close. Delegates to the synchronous :meth:`close`
        since the underlying NNG close operation is non-blocking."""
        self.close()


class Listener:
    """Base class for NNG listeners."""

    local_address = SockAddrOption("local-address")
    remote_address = SockAddrOption("remote-address")
    reconnect_time_min = MsOption("reconnect-time-min")
    reconnect_time_max = MsOption("reconnect-time-max")
    recv_max_size = SizeOption("recv-size-max")
    url = StringOption("url")
    peer = IntOption("peer")
    peer_name = StringOption("peer-name")
    tcp_nodelay = BooleanOption("tcp-nodelay")
    tcp_keepalive = BooleanOption("tcp-keepalive")

    def __init__(self, listener, socket):
        """
        Args:
            listener: the initialized `lib.nng_listener`.
            socket: The Socket associated with the listener

        """
        self._listener = listener
        self.socket = socket

    @property
    def _lib(self):
        return self.socket._lib

    @property
    def _ffi(self):
        return self.socket._ffi

    @property
    def listener(self):
        return self._listener[0]

    def close(self):
        """
        Close the listener.
        """
        self._lib.nng_listener_close(self.listener)
        self.socket._listeners.pop(self.id, None)

    @property
    def id(self):
        return self._lib.nng_listener_id(self.listener)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self.close()

    async def aclose(self):
        """Asynchronous close. Delegates to the synchronous :meth:`close`
        since the underlying NNG close operation is non-blocking."""
        self.close()


class Pipe:
    """Base class for NNG pipes."""

    local_address = SockAddrOption("local-address")
    remote_address = SockAddrOption("remote-address")
    url = StringOption("url")
    protocol = IntOption("protocol")
    protocol_name = StringOption("protocol-name")
    peer = IntOption("peer")
    peer_name = StringOption("peer-name")
    tcp_nodelay = BooleanOption("tcp-nodelay")
    tcp_keepalive = BooleanOption("tcp-keepalive")

    def __init__(self, lib_pipe, socket):
        _ffi = socket._ffi
        self._pipe = _ffi.new("nng_pipe *")
        self._pipe[0] = lib_pipe
        self.pipe = self._pipe[0]
        self.socket = socket
        self._closed = False

    @property
    def _lib(self):
        return self.socket._lib

    @property
    def _ffi(self):
        return self.socket._ffi

    @property
    def closed(self):
        """
        Return whether the pipe has been closed directly.

        This will not be valid if the pipe was closed indirectly, e.g. by
        closing the associated listener/dialer/socket.

        """
        return self._closed

    @property
    def id(self):
        return self._lib.nng_pipe_id(self.pipe)

    @property
    def dialer(self):
        """
        Return the dialer this pipe is associated with.  If the pipe is not
        associated with a dialer, raise an exception

        """
        _lib = self._lib
        dialer = _lib.nng_pipe_dialer(self.pipe)
        d_id = _lib.nng_dialer_id(dialer)
        if d_id < 0:
            raise TypeError("This pipe has no associated dialers.")
        return self.socket._dialers[d_id]

    @property
    def listener(self):
        """
        Return the listener this pipe is associated with.  If the pipe is not
        associated with a listener, raise an exception

        """
        _lib = self._lib
        listener = _lib.nng_pipe_listener(self.pipe)
        l_id = _lib.nng_listener_id(listener)
        if l_id < 0:
            raise TypeError("This pipe has no associated listeners.")
        return self.socket._listeners[l_id]

    def close(self):
        """
        Close the pipe.

        """
        from .exceptions import check_err

        check_err(self._lib.nng_pipe_close(self.pipe))
        self._closed = True

    def send(self, data):
        """
        Synchronously send bytes from this :class:`Pipe`.  This method
        automatically creates a :class:`Message`, associates with this pipe,
        and sends it with this pipe's associated :class:`Socket`.

        """
        _ensure_can_send(data)
        msg_cls = self.socket._message_class or Message
        msg = msg_cls(data, self, _lib=self._lib, _ffi=self._ffi)
        self.socket.send_msg(msg)

    def send_msg(self, msg):
        """
        Synchronously send a Message from this :class:`Pipe`.

        """
        msg.pipe = self
        self.socket.send_msg(msg)

    async def asend(self, data):
        """
        Asynchronously send bytes from this :class:`Pipe`.

        """
        _ensure_can_send(data)
        msg_cls = self.socket._message_class or Message
        msg = msg_cls(data, self, _lib=self._lib, _ffi=self._ffi)
        return await self.socket.asend_msg(msg)

    async def asend_msg(self, msg):
        """
        Asynchronously send a Message from this :class:`Pipe`.

        """
        msg.pipe = self
        return await self.socket.asend_msg(msg)


class Context:
    """Base class for NNG contexts."""

    recv_timeout = MsOption("recv-timeout")
    send_timeout = MsOption("send-timeout")

    def __init__(self, socket):
        _check_fork()
        _mark_nng_initialized()
        # need to set attributes first, so that if anything goes wrong,
        # __del__() doesn't throw an AttributeError
        self._context = None
        assert isinstance(socket, Socket)
        self._socket = socket
        _ffi = socket._ffi
        _lib = socket._lib
        from .exceptions import check_err

        self._context = _ffi.new("nng_ctx *")
        check_err(_lib.nng_ctx_open(self._context, socket.socket))
        self._recv_pool = []
        self._send_pool = []

        assert _lib.nng_ctx_id(self.context) != -1

    @property
    def _lib(self):
        return self._socket._lib

    @property
    def _ffi(self):
        return self._socket._ffi

    _MAX_POOL_SIZE = 32

    def _acquire_recv_helper(self):
        pool = self._recv_pool
        while pool:
            helper = pool.pop()
            if helper.is_valid_for_current_loop():
                return helper
            helper._free()
        return _aio.AIOHelper(self, self._socket._async_backend)

    def _release_recv_helper(self, helper):
        if (
            self._context is not None
            and len(self._recv_pool) < self._MAX_POOL_SIZE
            and helper.is_valid_for_current_loop()
        ):
            self._recv_pool.append(helper)
        else:
            helper._free()

    def _acquire_send_helper(self):
        pool = self._send_pool
        while pool:
            helper = pool.pop()
            if helper.is_valid_for_current_loop():
                return helper
            helper._free()
        return _aio.AIOHelper(self, self._socket._async_backend)

    def _release_send_helper(self, helper):
        if (
            self._context is not None
            and len(self._send_pool) < self._MAX_POOL_SIZE
            and helper.is_valid_for_current_loop()
        ):
            self._send_pool.append(helper)
        else:
            helper._free()

    async def arecv(self):
        """Asynchronously receive data using this context."""
        msg = await self.arecv_msg()
        return msg.bytes

    async def asend(self, data):
        """Asynchronously send data using this context."""
        _ensure_can_send(data)
        helper = self._acquire_send_helper()
        try:
            return await helper.asend(data)
        finally:
            self._release_send_helper(helper)

    def recv_msg(self, block=True):
        """Synchronously receive a :class:`Message` using this context."""
        _check_fork()
        _ffi = self._ffi
        _lib = self._lib
        from .exceptions import Timeout, TryAgain

        if not block:
            timeout = 0
        else:
            timeout = self.recv_timeout

        try:
            nng_msg = _sliced_aio_recv(
                _lib.nng_ctx_recv, self.context, _lib, _ffi, timeout
            )
        except Timeout:
            if not block:
                raise TryAgain(
                    "No message available immediately on context", _lib.NNG_EAGAIN
                )
            raise
        msg_cls = self._socket._message_class or Message
        msg = msg_cls(nng_msg, _lib=_lib, _ffi=_ffi)
        self._socket._try_associate_msg_with_pipe(msg)
        return msg

    def recv(self, block=True):
        """Synchronously receive data on this context."""
        msg = self.recv_msg(block=block)
        return msg.bytes

    def recv_into(self, buffer, block=True):
        """Receive data directly into the provided writable buffer."""
        m = memoryview(buffer)
        if m.readonly:
            raise BufferError("buffer must be writable")
        msg = self.recv_msg(block=block)
        with msg._mem_freed_lock:
            body = self._lib.nng_msg_body(msg._nng_msg)
            msg_len = self._lib.nng_msg_len(msg._nng_msg)
            nbytes = min(len(m), msg_len)
            c_buf = self._ffi.from_buffer(m)
            self._ffi.memmove(c_buf, body, nbytes)
        return nbytes

    def recv_nowait(self):
        """Receive data using this context without blocking.

        Equivalent to ``recv(block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv(block=False)

    def send_nowait(self, data):
        """Send data using this context without blocking.

        Equivalent to ``send(data, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if the send buffer is full.
        """
        return self.send(data, block=False)

    def recv_msg_nowait(self):
        """Receive a :class:`Message` using this context without blocking.

        Equivalent to ``recv_msg(block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv_msg(block=False)

    def send_msg_nowait(self, msg):
        """Send a :class:`Message` using this context without blocking.

        Equivalent to ``send_msg(msg, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if the send buffer is full.
        """
        return self.send_msg(msg, block=False)

    def recv_into_nowait(self, buffer):
        """Receive data directly into buffer using this context without blocking.

        Equivalent to ``recv_into(buffer, block=False)``. Raises :class:`pynng.TryAgain`
        immediately if no message is available.
        """
        return self.recv_into(buffer, block=False)

    async def arecv_into(self, buffer):
        """Asynchronously receive data directly into the provided writable buffer."""
        m = memoryview(buffer)
        if m.readonly:
            raise BufferError("buffer must be writable")
        msg = await self.arecv_msg()
        with msg._mem_freed_lock:
            body = self._lib.nng_msg_body(msg._nng_msg)
            msg_len = self._lib.nng_msg_len(msg._nng_msg)
            nbytes = min(len(m), msg_len)
            c_buf = self._ffi.from_buffer(m)
            self._ffi.memmove(c_buf, body, nbytes)
        return nbytes

    def send_msg(self, msg, block=True):
        """Synchronously send the :class:`Message` ``msg`` on the context."""
        _ffi = self._ffi
        _lib = self._lib
        from .exceptions import check_err, TryAgain

        with msg._mem_freed_lock:
            msg._ensure_can_send()
            aio_p = _ffi.new("nng_aio **")
            check_err(
                _lib.nng_aio_alloc(aio_p, _ffi.NULL, _ffi.NULL),
                lib=_lib,
                ffi=_ffi,
            )
            aio = aio_p[0]
            try:
                _lib.nng_aio_set_msg(aio, msg._nng_msg)
                if not block:
                    _lib.nng_aio_set_timeout(aio, 0)
                _lib.nng_ctx_send(self.context, aio)
                _lib.nng_aio_wait(aio)
                res = _lib.nng_aio_result(aio)
                if res != 0:
                    # nng retains the message on the aio when send fails; detach it
                    # so Message retains ownership and frees it in __del__ (or allows retry).
                    _lib.nng_aio_set_msg(aio, _ffi.NULL)
                    if not block and res == _lib.NNG_ETIMEDOUT:
                        raise TryAgain("Context send buffer full", _lib.NNG_EAGAIN)
                    check_err(res, lib=_lib, ffi=_ffi)
                msg._mem_freed = True
            finally:
                _lib.nng_aio_free(aio)

    def send(self, data, block=True):
        """
        Synchronously send data on the context.

        """
        _ensure_can_send(data)
        msg_cls = self._socket._message_class or Message
        msg = msg_cls(data, _lib=self._lib, _ffi=self._ffi)
        return self.send_msg(msg, block=block)

    def close(self):
        """Close this context."""
        _lib = self._lib
        from .exceptions import check_err

        ctx_err = 0
        while self._recv_pool:
            self._recv_pool.pop()._free()
        while self._send_pool:
            self._send_pool.pop()._free()
        if self._context is not None:
            # check that nng still has a reference
            if _lib.nng_ctx_id(self.context) != -1:
                ctx_err = _lib.nng_ctx_close(self.context)
                self._context = None
                check_err(ctx_err)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        """Close the context. Delegates to synchronous close() since the
        underlying NNG close operation is non-blocking."""
        self.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        import pynng

        try:
            return await self.arecv()
        except pynng.Closed:
            raise StopAsyncIteration

    async def aclose(self):
        """Asynchronous close. Delegates to the synchronous :meth:`close`
        since the underlying NNG close operation is non-blocking."""
        self.close()

    @property
    def context(self):
        """Return the underlying nng object."""
        return self._context[0]

    def __del__(self):
        if _is_nng_finalized():
            return
        try:
            self.close()
        except (TypeError, AttributeError, NNGException):
            pass

    async def asend_msg(self, msg):
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

    async def arecv_msg(self):
        """
        Asynchronously receive a :class:`Message` on the context.
        """
        helper = self._acquire_recv_helper()
        try:
            msg = await helper.arecv_msg()
            self._socket._try_associate_msg_with_pipe(msg)
            return msg
        finally:
            self._release_recv_helper(helper)


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

    def __init__(self, data, pipe=None, *, _lib=None, _ffi=None):
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

        self.__lib = _lib
        self.__ffi = _ffi
        self._mem_freed = False
        self._mem_freed_lock = threading.Lock()
        self._nng_msg = None

        from .exceptions import check_err

        if (
            isinstance(data, _ffi.CData)
            and _ffi.typeof(data).cname == "struct nng_msg *"
        ):
            self._nng_msg = data
        else:
            _ensure_can_send(data)
            m = memoryview(data)
            if isinstance(data, bytes):
                c_buf = data
            else:
                c_buf = _ffi.from_buffer(m)
            msg_p = _ffi.new("nng_msg **")
            check_err(_lib.nng_msg_alloc(msg_p, 0))
            msg = msg_p[0]
            try:
                check_err(_lib.nng_msg_append(msg, c_buf, len(m)))
            except Exception:
                _lib.nng_msg_free(msg)
                raise
            self._nng_msg = msg

        if pipe is None:
            self._pipe = None
        else:
            self.pipe = pipe

    @property
    def _lib(self):
        return self.__lib

    @property
    def _ffi(self):
        return self.__ffi

    @property
    def pipe(self):
        return self._pipe

    @pipe.setter
    def pipe(self, pipe):
        if not isinstance(pipe, Pipe):
            msg = "pipe must be type Pipe, not {}".format(type(pipe))
            raise ValueError(msg)
        from .exceptions import check_err

        check_err(self.__lib.nng_msg_set_pipe(self._nng_msg, pipe.pipe))
        self._pipe = pipe

    @property
    def _buffer(self):
        """
        Returns a cffi.buffer to the underlying nng_msg buffer.

        If you access the message's buffer using this property, you must ensure
        that you do not send the message until you are not using the buffer
        anymore.

        """
        import pynng

        _lib = self.__lib
        _ffi = self.__ffi
        with self._mem_freed_lock:
            if self._mem_freed:
                raise pynng.MessageStateError(
                    "Message buffer is no longer available after sending."
                )
            size = _lib.nng_msg_len(self._nng_msg)
            data = _ffi.cast("char *", _lib.nng_msg_body(self._nng_msg))
            return _ffi.buffer(data[0:size])

    @property
    def bytes(self):
        """
        Return the bytes from the underlying buffer.

        """
        return bytes(self._buffer)

    @property
    def header(self):
        """Return the bytes from the message header."""
        import pynng

        _lib = self.__lib
        _ffi = self.__ffi
        with self._mem_freed_lock:
            if self._mem_freed:
                raise pynng.MessageStateError(
                    "Message header is no longer available after sending."
                )
            size = _lib.nng_msg_header_len(self._nng_msg)
            if size == 0:
                return b""
            data = _ffi.cast("char *", _lib.nng_msg_header(self._nng_msg))
            return bytes(_ffi.buffer(data[0:size]))

    def header_append(self, data):
        """Append data to the message header.

        Args:
            data: Any buffer-protocol object (e.g. bytes, bytearray, memoryview).
        """
        _lib = self.__lib
        _ffi = self.__ffi
        from .exceptions import check_err

        with self._mem_freed_lock:
            self._ensure_can_send()
            m = memoryview(data)
            if isinstance(data, bytes):
                c_buf = data
            else:
                c_buf = _ffi.from_buffer(m)
            check_err(_lib.nng_msg_header_append(self._nng_msg, c_buf, len(m)))

    def header_trim(self, sz):
        """Trim sz bytes from the start of the message header."""
        _lib = self.__lib
        from .exceptions import check_err

        with self._mem_freed_lock:
            self._ensure_can_send()
            check_err(_lib.nng_msg_header_trim(self._nng_msg, sz))

    def header_chop(self, sz):
        """Chop sz bytes from the end of the message header."""
        _lib = self.__lib
        from .exceptions import check_err

        with self._mem_freed_lock:
            self._ensure_can_send()
            check_err(_lib.nng_msg_header_chop(self._nng_msg, sz))

    def header_clear(self):
        """Clear all data from the message header."""
        _lib = self.__lib
        with self._mem_freed_lock:
            self._ensure_can_send()
            _lib.nng_msg_header_clear(self._nng_msg)

    def copy(self):
        """Create a duplicate copy of this message."""
        _lib = self.__lib
        _ffi = self.__ffi
        import pynng
        from .exceptions import check_err

        with self._mem_freed_lock:
            if self._mem_freed:
                raise pynng.MessageStateError(
                    "Cannot copy a message that has already been sent."
                )
            dup_p = _ffi.new("nng_msg **")
            check_err(_lib.nng_msg_dup(dup_p, self._nng_msg))
            msg_cls = type(self)
            return msg_cls(dup_p[0], pipe=self._pipe, _lib=_lib, _ffi=_ffi)

    def dup(self):
        """Alias for :meth:`copy`."""
        return self.copy()

    def __del__(self):
        if _is_nng_finalized():
            return
        if not hasattr(self, "_mem_freed_lock"):
            return
        with self._mem_freed_lock:
            if self._mem_freed:
                return
            else:
                if getattr(self, "_nng_msg", None) is not None:
                    self.__lib.nng_msg_free(self._nng_msg)
                self._mem_freed = True

    def _ensure_can_send(self):
        """
        Raises an exception if the message's state is such that it cannot be
        sent.  The _mem_freed_lock() must be acquired when this method is
        called.

        """
        import pynng

        assert self._mem_freed_lock.locked()
        if self._mem_freed:
            msg = "Attempted to send the same message more than once."
            raise pynng.MessageStateError(msg)
