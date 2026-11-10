"""
nng v2 protocol classes.

Provides all 11 v2 protocol subclasses, plus v2-specific Socket, Dialer,
Listener, Pipe, Context, and Message classes.

.. warning:: nng v2 is experimental/alpha. The API may change between releases.
"""

from __future__ import annotations

import atexit
from collections.abc import Callable, Iterable
import logging
import threading
from typing import TYPE_CHECKING, ClassVar, TypeVar, cast

import pynng
from pynng import (
    _aio,  # noqa: F401
    _base,
    options,  # noqa: F401
    service as _service_mod,
    sockaddr as _sockaddr,
)
from pynng._base import (  # noqa: F401
    BooleanOption,
    IntOption,
    MsOption,
    NotImplementedOption,
    PipeEvent as _BasePipeEvent,
    PipeEventStream as _BasePipeEventStream,
    PointerOption,
    ReadOnlyBooleanOption,
    ReadOnlyIntOption,
    ReadOnlyStringOption,
    SizeOption,
    SockAddrOption,
    StringOption,
    _do_callbacks,
    _ensure_can_send,
    _NNGOption,
    _ReadOnlyOption,
    to_char,
)
from pynng._finalized import retain_closed as _retain_closed
from pynng._nng_v2 import ffi, lib
from pynng.exceptions import BadState, Closed, Timeout, check_err
from pynng.nng import _adevice, _device
from pynng.stats import Stat, _socket_stats, _stats
from pynng.tls import TLSConfig as _BaseTLSConfig

if TYPE_CHECKING:
    import cffi

    from pynng import _nng_v2
    from pynng.sockaddr import SockAddr

_EndpointT = TypeVar("_EndpointT", "_nng_v2.nng_dialer", "_nng_v2.nng_listener")

logger = logging.getLogger(__name__)

_c_lib: _nng_v2._Lib = lib
_c_ffi: cffi.FFI = ffi

__all__ = [
    "Bus0",
    "Context",
    "Dialer",
    "Listener",
    "Message",
    "Pair0",
    "Pair1",
    "Pipe",
    "PipeEvent",
    "PipeEventStream",
    "Pub0",
    "Pull0",
    "Push0",
    "RawBus0",
    "RawPair0",
    "RawPair1",
    "RawPub0",
    "RawPull0",
    "RawPush0",
    "RawRep0",
    "RawReq0",
    "RawRespondent0",
    "RawSub0",
    "RawSurveyor0",
    "Rep0",
    "Rep0Service",
    "Req0",
    "Respondent0",
    "Socket",
    "Stat",
    "Sub0",
    "Surveyor0",
    "TLSConfig",
    "adevice",
    "device",
    "ffi",
    "lib",
    "nng_fini",
    "nng_fini_at_exit",
    "socket_stats",
    "stats",
]

# Flag to allow users who explicitly need nng_fini() at atexit to opt in.
# Defaults to False to avoid process-crashing race conditions with Python GC.
nng_fini_at_exit: bool = False
_finalized: bool = False


def nng_fini() -> None:
    """Explicitly finalize the nng v2 library runtime."""
    global _finalized
    if not _finalized:
        _finalized = True
        lib.nng_fini()


def _pynng_v2_atexit() -> None:
    if nng_fini_at_exit:
        nng_fini()


atexit.register(_pynng_v2_atexit)


class TLSConfig(_BaseTLSConfig):
    """TLS configuration for nng v2 endpoints."""

    MODE_CLIENT: int = lib.NNG_TLS_MODE_CLIENT
    MODE_SERVER: int = lib.NNG_TLS_MODE_SERVER

    AUTH_MODE_NONE: int = lib.NNG_TLS_AUTH_MODE_NONE
    AUTH_MODE_OPTIONAL: int = lib.NNG_TLS_AUTH_MODE_OPTIONAL
    AUTH_MODE_REQUIRED: int = lib.NNG_TLS_AUTH_MODE_REQUIRED

    _lib: ClassVar[_base._NngLib] = lib
    _ffi: ClassVar[cffi.FFI] = ffi


class Socket(_base.Socket):
    """v2 socket base class.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.

    v2 sockets differ from v1 in several ways:

    - ``close()`` uses ``nng_socket_close()`` instead of ``nng_close()``
    - ``recv()`` uses ``nng_recvmsg()`` (no ``NNG_FLAG_ALLOC`` in v2)
    - Protocol/peer info uses dedicated functions instead of option accessors
    - No ``name`` property (``NNG_OPT_SOCKNAME`` removed in v2)
    - TLS configuration is per-endpoint. A ``tls_config`` given to the socket
      is the default for its endpoints: it is applied to each endpoint whose
      transport supports TLS, and endpoints of other transports (such as
      ``tcp://``, ``ipc://`` and ``inproc://``) ignore it, as in v1
    """

    _lib: ClassVar[_base._NngLib] = lib
    _ffi: ClassVar[cffi.FFI] = ffi
    _version_tag = "v2"

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
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        self._tls_config: _BaseTLSConfig | None = None
        if tls_config is not None:
            self.tls_config = tls_config
        super().__init__(
            dial=None,
            listen=None,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
        )
        if listen is not None:
            self.listen(listen)
        if dial is not None:
            self.dial(dial, block=block_on_dial)

    @property
    def tls_config(self) -> _BaseTLSConfig | None:
        """Default :class:`TLSConfig` for new endpoints whose transport has TLS."""
        return getattr(self, "_tls_config", None)

    @tls_config.setter
    def tls_config(self, value: _BaseTLSConfig | None) -> None:
        if value is not None and not isinstance(value, _BaseTLSConfig):
            raise ValueError(
                f"Invalid value {value} of type {type(value)}.  Expected TLSConfig."
            )
        self._tls_config = value
        if value is not None:
            _retain_closed(value)

    def dial(
        self,
        address: str | bytes,
        *,
        block: bool | None = None,
        tls_config: _BaseTLSConfig | None = None,
        start: bool = True,
    ) -> Dialer:
        """Dial the specified address.

        Args:
            address: The address to dial.
            block: As for :meth:`pynng.Socket.dial`.
            tls_config: The :class:`TLSConfig` for this dialer. If None, the
                socket's :attr:`tls_config` is used when the transport
                supports TLS.
            start: If False, create the dialer without starting it; start it
                later with :meth:`Dialer.start`.
        """
        _base._check_fork()
        if not start:
            return self._dial(address, flags=0, tls_config=tls_config, start=False)
        if block:
            return self._dial(address, flags=0, tls_config=tls_config)
        elif block is None:
            try:
                return self.dial(address, block=True, tls_config=tls_config)
            except pynng.ConnectionRefused:
                msg = "Synchronous dial failed; attempting asynchronous now"
                logger.exception(msg)
                return self.dial(address, block=False, tls_config=tls_config)
        else:
            return self._dial(
                address, flags=lib.NNG_FLAG_NONBLOCK, tls_config=tls_config
            )

    def _endpoint_tls(
        self, tls_config: _BaseTLSConfig | None
    ) -> tuple[_BaseTLSConfig | None, bool]:
        """Return ``(config, explicit)`` for a new endpoint."""
        if tls_config is not None:
            if not isinstance(tls_config, _BaseTLSConfig):
                raise ValueError(
                    f"Invalid value {tls_config} of type {type(tls_config)}.  "
                    "Expected TLSConfig."
                )
            return tls_config, True
        return self.tls_config, False

    @staticmethod
    def _set_endpoint_tls(
        set_tls: Callable[[_EndpointT, _nng_v2.nng_tls_config], int],
        endpoint: _EndpointT,
        tls_config: _BaseTLSConfig,
        explicit: bool,
    ) -> bool:
        """Apply ``tls_config`` to an endpoint; return whether it was applied.

        The socket default is skipped on transports without TLS, which is what
        nng v1 does for a socket-level TLS config. An explicit config fails.
        """
        cfg = cast("_nng_v2.nng_tls_config", tls_config._config_for(lib, ffi))
        err = set_tls(endpoint, cfg)
        if err == lib.NNG_ENOTSUP and not explicit:
            return False
        check_err(err, lib=lib, ffi=ffi)
        return True

    def _dial(
        self,
        address: str | bytes,
        flags: int = 0,
        *,
        tls_config: _BaseTLSConfig | None = None,
        start: bool = True,
    ) -> Dialer:
        tls_config, explicit = self._endpoint_tls(tls_config)
        dialer = _c_ffi.new("nng_dialer *")
        addr_ptr = to_char(address, ffi=ffi)
        tls_applied = False
        if tls_config is not None or not start:
            check_err(
                _c_lib.nng_dialer_create(dialer, self.socket, addr_ptr),
                lib=lib,
                ffi=ffi,
            )
            try:
                if tls_config is not None:
                    tls_applied = self._set_endpoint_tls(
                        _c_lib.nng_dialer_set_tls, dialer[0], tls_config, explicit
                    )
                if start:
                    check_err(
                        _c_lib.nng_dialer_start(dialer[0], flags), lib=lib, ffi=ffi
                    )
            except BaseException:
                _c_lib.nng_dialer_close(dialer[0])
                raise
        else:
            check_err(
                _c_lib.nng_dial(self.socket, addr_ptr, dialer, flags),
                lib=lib,
                ffi=ffi,
            )
        d_id = int(_c_lib.nng_dialer_id(dialer[0]))
        dialer_cls = self._dialer_class or Dialer
        py_dialer = dialer_cls(dialer, self)
        assert isinstance(py_dialer, Dialer)
        if tls_applied and tls_config is not None:
            py_dialer._tls_config_ref = tls_config
            _retain_closed(tls_config)
        self._dialers[d_id] = py_dialer
        return py_dialer

    def listen(
        self,
        address: str | bytes,
        flags: int = 0,
        *,
        tls_config: _BaseTLSConfig | None = None,
        start: bool = True,
    ) -> Listener:
        """Listen at the specified address.

        Args:
            address: The address to listen on.
            flags: Flags passed to ``nng_listener_start``.
            tls_config: The :class:`TLSConfig` for this listener. If None, the
                socket's :attr:`tls_config` is used when the transport
                supports TLS.
            start: If False, create the listener without starting it; start
                it later with :meth:`Listener.start`.
        """
        _base._check_fork()
        tls_config, explicit = self._endpoint_tls(tls_config)
        listener = _c_ffi.new("nng_listener *")
        addr_ptr = to_char(address, ffi=ffi)
        tls_applied = False
        if tls_config is not None or not start:
            check_err(
                _c_lib.nng_listener_create(listener, self.socket, addr_ptr),
                lib=lib,
                ffi=ffi,
            )
            try:
                if tls_config is not None:
                    tls_applied = self._set_endpoint_tls(
                        _c_lib.nng_listener_set_tls, listener[0], tls_config, explicit
                    )
                if start:
                    check_err(
                        _c_lib.nng_listener_start(listener[0], flags), lib=lib, ffi=ffi
                    )
            except BaseException:
                _c_lib.nng_listener_close(listener[0])
                raise
        else:
            check_err(
                _c_lib.nng_listen(self.socket, addr_ptr, listener, flags),
                lib=lib,
                ffi=ffi,
            )
        l_id = int(_c_lib.nng_listener_id(listener[0]))
        listener_cls = self._listener_class or Listener
        py_listener = listener_cls(listener, self)
        assert isinstance(py_listener, Listener)
        if tls_applied and tls_config is not None:
            py_listener._tls_config_ref = tls_config
            _retain_closed(tls_config)
        self._listeners[l_id] = py_listener
        return py_listener

    @property
    def _aio_recv_fn(
        self,
    ) -> Callable[[_nng_v2.nng_socket, _nng_v2.nng_aio], None]:
        """Return the v2 AIO receive function for socket-level operations."""
        return lib.nng_socket_recv

    @property
    def _aio_send_fn(
        self,
    ) -> Callable[[_nng_v2.nng_socket, _nng_v2.nng_aio], None]:
        """Return the v2 AIO send function for socket-level operations."""
        return lib.nng_socket_send

    @property
    def protocol(self) -> int:
        """The 16-bit protocol number for this socket (read-only)."""
        proto_id = _c_ffi.new("uint16_t *")
        check_err(_c_lib.nng_socket_proto_id(self.socket, proto_id))
        return int(proto_id[0])

    @property
    def protocol_name(self) -> str:
        """The protocol name for this socket (read-only)."""
        name_p = _c_ffi.new("char **")
        check_err(_c_lib.nng_socket_proto_name(self.socket, name_p))
        raw = _c_ffi.string(name_p[0])
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    @property
    def peer(self) -> int:
        """The peer protocol id for this socket (read-only)."""
        peer_id = _c_ffi.new("uint16_t *")
        check_err(_c_lib.nng_socket_peer_id(self.socket, peer_id))
        return int(peer_id[0])

    @property
    def peer_name(self) -> str:
        """The peer protocol name for this socket (read-only)."""
        name_p = _c_ffi.new("char **")
        check_err(_c_lib.nng_socket_peer_name(self.socket, name_p))
        raw = _c_ffi.string(name_p[0])
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    @property
    def raw(self) -> bool:
        """Whether this socket is in raw mode (read-only)."""
        raw_p = _c_ffi.new("bool *")
        check_err(_c_lib.nng_socket_raw(self.socket, raw_p))
        return bool(raw_p[0])

    @property
    def recv_fd(self) -> int:
        """The receive poll file descriptor for this socket (read-only)."""
        fd_p = _c_ffi.new("int *")
        check_err(_c_lib.nng_socket_get_recv_poll_fd(self.socket, fd_p))
        return int(fd_p[0])

    @property
    def send_fd(self) -> int:
        """The send poll file descriptor for this socket (read-only)."""
        fd_p = _c_ffi.new("int *")
        check_err(_c_lib.nng_socket_get_send_poll_fd(self.socket, fd_p))
        return int(fd_p[0])

    def close(self) -> None:
        """Close the socket, freeing all system resources.

        This method is idempotent and thread-safe. Uses ``nng_socket_close()``
        (the v2 API).

        A call from a pipe callback returns at once, and the socket finishes
        closing on another thread after the running pipe callbacks return.
        """
        self._do_close(lib.nng_socket_close)

    def recv(self, block: bool = True) -> bytes:
        """Receive data on the socket.

        In v2, recv uses ``nng_recvmsg()`` since ``NNG_FLAG_ALLOC`` does not
        exist.

        Args:
            block: If True (default), blocks until data arrives or timeout.
                If False, returns immediately or raises ``pynng.TryAgain``.
        """
        msg = self.recv_msg(block=block)
        return msg.bytes

    def send(self, data: _base.ReadableBuffer, block: bool = True) -> None:
        """Send data on the socket.

        Args:
            data: bytes, bytearray, memoryview, or buffer-protocol object to send.
            block: If True (default), blocks until sent or timeout.
                If False, raises ``pynng.TryAgain`` if cannot send immediately
                (such as when the send buffer is full).

        .. note::

            In asynchronous code (asyncio/Trio), avoid calling synchronous
            ``send(data, block=True)`` when the send queue might fill, as it blocks
            the event loop thread. Use :meth:`~Socket.asend` or non-blocking
            ``send(data, block=False)`` instead.
        """
        _ensure_can_send(data)
        flags = 0
        if not block:
            flags |= lib.NNG_FLAG_NONBLOCK
        c_buf: bytes | cffi.FFI.CData
        if isinstance(data, bytes):
            c_buf = data
        else:
            c_buf = ffi.from_buffer(data)
        err = _c_lib.nng_send(self.socket, c_buf, len(data), flags)
        check_err(err)

    async def arecv(self) -> bytes:
        """Asynchronous version of :meth:`recv`."""
        msg = await self.arecv_msg()
        return msg.bytes

    async def asend(self, data: _base.ReadableBuffer) -> None:
        """Asynchronous version of :meth:`send`.

        Yields cooperatively to the event loop if the socket's send buffer
        (:attr:`~Socket.send_buffer_size`) is full, resuming as soon as buffer
        space becomes available without blocking other coroutines.
        """
        _ensure_can_send(data)
        helper = self._acquire_send_helper()
        try:
            return await helper.asend(data)
        finally:
            self._release_send_helper(helper)

    def stats(self) -> Stat | None:
        """Get snapshot of statistics for this socket."""
        return socket_stats(self)

    def stat(self, name: str) -> int | str | bool | None:
        """Get a single statistic value by name for this socket."""
        st = socket_stats(self)
        assert st is not None
        child = st[name]
        assert isinstance(child, Stat)
        return child.value

    if TYPE_CHECKING:

        @property
        def socket(self) -> _nng_v2.nng_socket: ...

        def recv_msg(self, block: bool = True) -> Message: ...

        def recv_msg_nowait(self) -> Message: ...

        async def arecv_msg(self) -> Message: ...

        @property
        def dialers(self) -> tuple[Dialer, ...]: ...

        @property
        def listeners(self) -> tuple[Listener, ...]: ...

        @property
        def pipes(self) -> tuple[Pipe, ...]: ...

        def new_context(self) -> Context: ...

        def add_pre_pipe_connect_cb(
            self, callback: Callable[[Pipe], object]
        ) -> None: ...

        def add_post_pipe_connect_cb(
            self, callback: Callable[[Pipe], object]
        ) -> None: ...

        def add_post_pipe_remove_cb(
            self, callback: Callable[[Pipe], object]
        ) -> None: ...

        def remove_pre_pipe_connect_cb(
            self, callback: Callable[[Pipe], object]
        ) -> None: ...

        def remove_post_pipe_connect_cb(
            self, callback: Callable[[Pipe], object]
        ) -> None: ...

        def remove_post_pipe_remove_cb(
            self, callback: Callable[[Pipe], object]
        ) -> None: ...

        def pipe_events(self) -> PipeEventStream: ...


class Bus0(Socket):
    """A v2 bus0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _opener: _base._OpenerFn | None = lib.nng_bus0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_bus0_open_raw

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
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class Pair0(Socket):
    """A v2 pair0 socket for bidirectional one-to-one communication.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _opener: _base._OpenerFn | None = lib.nng_pair0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_pair0_open_raw

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
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class Pair1(Socket):
    """A v2 pair1 socket for bidirectional communication.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.

    Accepts a ``polyamorous`` keyword argument. If True, uses
    ``nng_pair1_open_poly`` to allow multiple peers.
    """

    def __init__(
        self,
        *,
        polyamorous: bool = False,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        if opener is None:
            if raw:
                opener = lib.nng_pair1_open_raw
            elif polyamorous:
                opener = lib.nng_pair1_open_poly
            else:
                opener = lib.nng_pair1_open
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )

    polyamorous = BooleanOption("pair1:polyamorous")


class Push0(Socket):
    """A v2 push0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _opener: _base._OpenerFn | None = lib.nng_push0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_push0_open_raw

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
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class Pull0(Socket):
    """A v2 pull0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _opener: _base._OpenerFn | None = lib.nng_pull0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_pull0_open_raw

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
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class Pub0(Socket):
    """A v2 pub0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _opener: _base._OpenerFn | None = lib.nng_pub0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_pub0_open_raw

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
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class Sub0(Socket):
    """A v2 sub0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.

    In v2, subscribe/unsubscribe uses dedicated functions
    (``nng_sub0_socket_subscribe``/``nng_sub0_socket_unsubscribe``)
    instead of option setters.
    """

    _opener: _base._OpenerFn | None = lib.nng_sub0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_sub0_open_raw

    def __init__(
        self,
        *,
        topics: str | bytes | Iterable[str | bytes] | None = None,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        self._subscriptions: set[bytes] = set()
        self._sub_lock = threading.RLock()
        self._init_topics = topics
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )

    def _configure_protocol_options(self) -> None:
        topics = self._init_topics
        self._init_topics = None
        if topics is not None:
            if isinstance(topics, (str, bytes)):
                topics = [topics]
            for topic in topics:
                self.subscribe(topic)

    @property
    def subscriptions(self) -> frozenset[bytes]:
        """Return a frozenset of current subscriptions (as bytes)."""
        with self._sub_lock:
            return frozenset(self._subscriptions)

    def subscribe(self, topic: str | bytes) -> None:
        """Subscribe to the specified topic.

        Uses the v2 dedicated function ``nng_sub0_socket_subscribe()``.

        Args:
            topic: str or bytes topic to subscribe to. Strings are
                automatically encoded to bytes.
        """
        if isinstance(topic, str):
            topic = topic.encode()
        check_err(_c_lib.nng_sub0_socket_subscribe(self.socket, topic, len(topic)))
        with self._sub_lock:
            self._subscriptions.add(topic)

    def unsubscribe(self, topic: str | bytes) -> None:
        """Unsubscribe from the specified topic.

        Uses the v2 dedicated function ``nng_sub0_socket_unsubscribe()``.

        Args:
            topic: str or bytes topic to unsubscribe from. Strings are
                automatically encoded to bytes.
        """
        if isinstance(topic, str):
            topic = topic.encode()
        check_err(_c_lib.nng_sub0_socket_unsubscribe(self.socket, topic, len(topic)))
        with self._sub_lock:
            self._subscriptions.discard(topic)

    def subscribe_all(self, topics: Iterable[str | bytes]) -> None:
        """Subscribe to multiple topics at once.

        Args:
            topics: An iterable of :class:`str` or :class:`bytes` topics.
        """
        for topic in topics:
            self.subscribe(topic)

    def unsubscribe_all(self) -> None:
        """Unsubscribe from all current subscriptions."""
        with self._sub_lock:
            current = list(self._subscriptions)
        for topic in current:
            self.unsubscribe(topic)


class Req0(Socket):
    """A v2 req0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    resend_time = MsOption("req:resend-time")
    _opener: _base._OpenerFn | None = lib.nng_req0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_req0_open_raw

    def __init__(
        self,
        *,
        resend_time: int | None = None,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )
        if resend_time is not None:
            self.resend_time = resend_time


class Rep0(Socket):
    """A v2 rep0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _opener: _base._OpenerFn | None = lib.nng_rep0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_rep0_open_raw

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
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class Surveyor0(Socket):
    """A v2 surveyor0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _opener: _base._OpenerFn | None = lib.nng_surveyor0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_surveyor0_open_raw
    _nonblock_recv_first = False
    survey_time = MsOption("surveyor:survey-time")

    def __init__(
        self,
        *,
        survey_time: int | None = None,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )
        if survey_time is not None:
            self.survey_time = survey_time

    async def asurvey(
        self,
        data: _base.ReadableBuffer,
        *,
        timeout: int | None = None,
        max_responses: int | None = None,
    ) -> list[bytes]:
        """Send a survey and collect all responses until timeout.

        Args:
            data: Survey message to send (bytes).
            timeout: Response collection timeout in ms. If None, uses
                the socket's recv_timeout.
            max_responses: Maximum number of responses to collect.

        Returns:
            list[bytes]: All responses received before timeout.
        """
        old_recv_timeout = self.recv_timeout
        old_survey_time = self.survey_time
        if timeout is not None:
            self.recv_timeout = timeout
            self.survey_time = timeout

        try:
            await self.asend(data)
            responses: list[bytes] = []
            while True:
                if max_responses is not None and len(responses) >= max_responses:
                    break
                try:
                    response = await self.arecv()
                    responses.append(response)
                except (Timeout, BadState):
                    break
            return responses
        finally:
            try:
                if timeout is not None:
                    self.recv_timeout = old_recv_timeout
                    self.survey_time = old_survey_time
            except Closed:
                pass


class Respondent0(Socket):
    """A v2 respondent0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _opener: _base._OpenerFn | None = lib.nng_respondent0_open
    _raw_opener: _base._OpenerFn | None = lib.nng_respondent0_open_raw

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
        opener: _base._OpenerFn | None = None,
        raw: bool = False,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawBus0(Bus0):
    """A raw v2 bus0 socket."""

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
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawPair0(Pair0):
    """A raw v2 pair0 socket."""

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
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawPair1(Pair1):
    """A raw v2 pair1 socket."""

    def __init__(
        self,
        *,
        polyamorous: bool = False,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            polyamorous=polyamorous,
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawPush0(Push0):
    """A raw v2 push0 socket."""

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
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawPull0(Pull0):
    """A raw v2 pull0 socket."""

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
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawPub0(Pub0):
    """A raw v2 pub0 socket."""

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
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawSub0(Sub0):
    """A raw v2 sub0 socket."""

    def __init__(
        self,
        *,
        topics: str | bytes | Iterable[str | bytes] | None = None,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            topics=topics,
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawReq0(Req0):
    """A raw v2 req0 socket."""

    def __init__(
        self,
        *,
        resend_time: int | None = None,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            resend_time=resend_time,
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawRep0(Rep0):
    """A raw v2 rep0 socket."""

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
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawSurveyor0(Surveyor0):
    """A raw v2 surveyor0 socket."""

    def __init__(
        self,
        *,
        survey_time: int | None = None,
        dial: str | bytes | None = None,
        listen: str | bytes | None = None,
        recv_timeout: int | None = None,
        send_timeout: int | None = None,
        recv_buffer_size: int | None = None,
        send_buffer_size: int | None = None,
        recv_max_size: int | None = None,
        reconnect_time_min: int | None = None,
        reconnect_time_max: int | None = None,
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            survey_time=survey_time,
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


class RawRespondent0(Respondent0):
    """A raw v2 respondent0 socket."""

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
        opener: _base._OpenerFn | None = None,
        raw: bool = True,
        block_on_dial: bool | None = None,
        async_backend: str | None = None,
        tls_config: _BaseTLSConfig | None = None,
    ) -> None:
        super().__init__(
            dial=dial,
            listen=listen,
            recv_timeout=recv_timeout,
            send_timeout=send_timeout,
            recv_buffer_size=recv_buffer_size,
            send_buffer_size=send_buffer_size,
            recv_max_size=recv_max_size,
            reconnect_time_min=reconnect_time_min,
            reconnect_time_max=reconnect_time_max,
            opener=opener,
            raw=raw,
            block_on_dial=block_on_dial,
            async_backend=async_backend,
            tls_config=tls_config,
        )


def _url_string(urlp: _nng_v2.nng_url) -> str:
    """Format an ``nng_url *`` with ``nng_url_sprintf``."""
    size = int(_c_lib.nng_url_sprintf(_c_ffi.NULL, 0, urlp)) + 1
    buf = _c_ffi.new("char[]", size)
    _c_lib.nng_url_sprintf(buf, size, urlp)
    raw = _c_ffi.string(buf)
    return raw.decode() if isinstance(raw, bytes) else str(raw)


class Dialer(_base.Dialer):
    """v2 dialer. Supports TLS configuration at the endpoint level.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _tls_config_ref: _BaseTLSConfig | None

    if TYPE_CHECKING:
        socket: Socket

        @property
        def dialer(self) -> _nng_v2.nng_dialer: ...

    @property
    def url(self) -> str:
        """The URL string for this dialer."""
        urlp = _c_ffi.new("struct nng_url **")
        check_err(_c_lib.nng_dialer_get_url(self.dialer, urlp), lib=lib, ffi=ffi)
        return _url_string(urlp[0])

    @property
    def tls_config(self) -> _BaseTLSConfig | None:
        """The :class:`TLSConfig` applied to this dialer, or None.

        None also when the dialer uses TLS with nng's default configuration.
        """
        return getattr(self, "_tls_config_ref", None)

    @tls_config.setter
    def tls_config(self, value: _BaseTLSConfig) -> None:
        if not isinstance(value, _BaseTLSConfig):
            raise ValueError(
                f"Invalid value {value} of type {type(value)}.  Expected TLSConfig."
            )
        cfg = cast("_nng_v2.nng_tls_config", value._config_for(lib, ffi))
        check_err(
            _c_lib.nng_dialer_set_tls(self.dialer, cfg),
            lib=lib,
            ffi=ffi,
        )
        self._tls_config_ref = value
        _retain_closed(value)

    def start(self, *, block: bool = True) -> None:
        """Start a dialer created with ``dial(..., start=False)``."""
        flags = 0 if block else lib.NNG_FLAG_NONBLOCK
        check_err(_c_lib.nng_dialer_start(self.dialer, flags), lib=lib, ffi=ffi)

    @property
    def local_address(self) -> SockAddr | None:
        """Local address for this dialer, if a connected pipe exists."""
        for pipe in self.socket.pipes:
            try:
                if pipe.dialer == self:
                    return pipe.local_address
            except (TypeError, KeyError):
                continue
        return None

    @property
    def remote_address(self) -> SockAddr | None:
        """Remote address for this dialer, if a connected pipe exists."""
        for pipe in self.socket.pipes:
            try:
                if pipe.dialer == self:
                    return pipe.remote_address
            except (TypeError, KeyError):
                continue
        return None


class Listener(_base.Listener):
    """v2 listener. Supports TLS configuration at the endpoint level.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    _tls_config_ref: _BaseTLSConfig | None

    if TYPE_CHECKING:
        socket: Socket

        @property
        def listener(self) -> _nng_v2.nng_listener: ...

    @property
    def url(self) -> str:
        """The URL string for this listener.

        After the listener starts, a TCP-based URL has the port that was bound,
        also when the URL asked for port 0.
        """
        urlp = _c_ffi.new("struct nng_url **")
        check_err(_c_lib.nng_listener_get_url(self.listener, urlp), lib=lib, ffi=ffi)
        return _url_string(urlp[0])

    @property
    def tls_config(self) -> _BaseTLSConfig | None:
        """The :class:`TLSConfig` applied to this listener, or None.

        None also when the listener uses TLS with nng's default configuration.
        """
        return getattr(self, "_tls_config_ref", None)

    @tls_config.setter
    def tls_config(self, value: _BaseTLSConfig) -> None:
        if not isinstance(value, _BaseTLSConfig):
            raise ValueError(
                f"Invalid value {value} of type {type(value)}.  Expected TLSConfig."
            )
        cfg = cast("_nng_v2.nng_tls_config", value._config_for(lib, ffi))
        check_err(
            _c_lib.nng_listener_set_tls(self.listener, cfg),
            lib=lib,
            ffi=ffi,
        )
        self._tls_config_ref = value
        _retain_closed(value)

    def start(self, flags: int = 0) -> None:
        """Start a listener created with ``listen(..., start=False)``."""
        check_err(_c_lib.nng_listener_start(self.listener, flags), lib=lib, ffi=ffi)

    @property
    def local_address(self) -> SockAddr | None:
        """Local address for this listener, if a connected pipe exists."""
        for pipe in self.socket.pipes:
            try:
                if pipe.listener == self:
                    return pipe.local_address
            except (TypeError, KeyError):
                continue
        return None

    @property
    def remote_address(self) -> SockAddr | None:
        """Remote address for this listener (not applicable)."""
        return None


class Context(_base.Context):
    """v2 context for multiplexing protocol state on a single socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    if TYPE_CHECKING:

        def recv_msg(self, block: bool = True) -> Message: ...

        def recv_msg_nowait(self) -> Message: ...

        async def arecv_msg(self) -> Message: ...


class Pipe(_base.Pipe):
    """v2 pipe representing a single connection between two endpoints.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    if TYPE_CHECKING:
        socket: Socket

        @property
        def pipe(self) -> _nng_v2.nng_pipe: ...

        @property
        def dialer(self) -> Dialer: ...

        @property
        def listener(self) -> Listener: ...

    @property
    def local_address(self) -> SockAddr:
        """The local address for this pipe."""
        sa = _c_ffi.new("nng_sockaddr *")
        check_err(_c_lib.nng_pipe_self_addr(self.pipe, sa))
        return _sockaddr._nng_sockaddr(sa, lib=lib)

    @property
    def remote_address(self) -> SockAddr:
        """The remote address for this pipe."""
        sa = _c_ffi.new("nng_sockaddr *")
        check_err(_c_lib.nng_pipe_peer_addr(self.pipe, sa))
        return _sockaddr._nng_sockaddr(sa, lib=lib)

    @property
    def scheme(self) -> str:
        """The transport scheme for this pipe (e.g. 'tcp', 'ipc')."""
        scheme_p = _c_ffi.new("char **")
        check_err(_c_lib.nng_pipe_get_scheme(self.pipe, scheme_p))
        raw = _c_ffi.string(scheme_p[0])
        return raw.decode() if isinstance(raw, bytes) else str(raw)


class PipeEvent(_BasePipeEvent["Pipe"]):
    """A v2 pipe event with a :class:`Pipe` and the event type."""

    __slots__ = ()


class PipeEventStream(_BasePipeEventStream["Pipe"]):
    """Async iterator that yields v2 :class:`PipeEvent` objects."""

    __slots__ = ()

    if TYPE_CHECKING:

        def __aiter__(self) -> PipeEventStream: ...

        async def __anext__(self) -> PipeEvent: ...

        async def __aenter__(self) -> PipeEventStream: ...


class Message(_base.Message):
    """v2 message.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    __slots__ = ()

    def __init__(
        self,
        data: _base.ReadableBuffer | _nng_v2.nng_msg | cffi.FFI.CData = b"",
        pipe: _base.Pipe | None = None,
        *,
        _lib: _base._NngLib | None = None,
        _ffi: cffi.FFI | None = None,
    ) -> None:
        super().__init__(data, pipe, _lib=_lib or lib, _ffi=_ffi or ffi)

    if TYPE_CHECKING:

        @property
        def pipe(self) -> Pipe | None: ...

        @pipe.setter
        def pipe(self, pipe: _base.Pipe) -> None: ...


class Rep0Service(_service_mod.Rep0Service):
    """High-level async REP service backed by a v2 :class:`Rep0` socket.

    The same as :class:`pynng.Rep0Service`, but a ``socket`` argument must be
    a :class:`pynng.v2.Rep0`.
    """

    _socket_class = Rep0


def stats() -> Stat:
    """Retrieve a snapshot of all v2 runtime statistics in the process."""
    return _stats(lib, ffi)


def socket_stats(
    sock: _base.Socket | _nng_v2.nng_socket | cffi.FFI.CData,
) -> Stat | None:
    """Retrieve statistics for a v2 socket.

    Args:
        sock: A v2 :class:`Socket` or a v2 ``nng_socket`` handle.

    Returns:
        Stat: The socket's stat subtree, or None if not found.
    """
    return _socket_stats(sock, lib, ffi)


def device(
    s1: _base.Socket | _nng_v2.nng_socket | cffi.FFI.CData,
    s2: _base.Socket | _nng_v2.nng_socket | cffi.FFI.CData | None = None,
) -> None:
    """Forward messages between v2 sockets; see :func:`pynng.device`.

    Closing either socket ends the device with :class:`Closed`. nng v2 gives
    the device both sockets, so when the device ends, nng closes both.
    """
    _device(s1, s2, lib, ffi)


async def adevice(
    s1: _base.Socket | _nng_v2.nng_socket | cffi.FFI.CData,
    s2: _base.Socket | _nng_v2.nng_socket | cffi.FFI.CData | None = None,
    *,
    async_backend: str | None = None,
) -> None:
    """Asynchronous version of :func:`device`; see :func:`pynng.adevice`."""
    await _adevice(s1, s2, async_backend, lib, ffi)


# Wire up v2-specific subclasses so base class factory methods
# create v2 types instead of _base types.
Socket._context_class = Context
Socket._pipe_class = Pipe
Socket._dialer_class = Dialer
Socket._listener_class = Listener
Socket._message_class = Message
Socket._pipe_event_class = PipeEvent
Socket._pipe_event_stream_class = PipeEventStream
