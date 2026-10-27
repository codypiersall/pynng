"""
nng v2 protocol classes.

Provides all 11 v2 protocol subclasses, plus v2-specific Socket, Dialer,
Listener, Pipe, Context, and Message classes.

.. warning:: nng v2 is experimental/alpha. The API may change between releases.
"""

import logging
import threading

import pynng
from pynng._nng_v2 import ffi, lib
from pynng.exceptions import check_err, Closed, BadState, Timeout
from pynng._finalized import retain_closed as _retain_closed
from pynng.tls import TLSConfig as _BaseTLSConfig
from pynng.stats import _stats, _socket_stats, Stat  # noqa: F401
from pynng.nng import _device, _adevice
from pynng._base import (
    _ensure_can_send,
    _do_callbacks,
    to_char,
    PipeEvent,
    PipeEventStream,
    _NNGOption,
    IntOption,
    MsOption,
    SockAddrOption,
    SizeOption,
    StringOption,
    BooleanOption,
    PointerOption,
    NotImplementedOption,
)
from pynng import _aio
from pynng import _base
from pynng import options
from pynng import service as _service_mod


logger = logging.getLogger(__name__)


class TLSConfig(_BaseTLSConfig):
    """TLS configuration for nng v2 endpoints."""

    MODE_CLIENT = lib.NNG_TLS_MODE_CLIENT
    MODE_SERVER = lib.NNG_TLS_MODE_SERVER

    AUTH_MODE_NONE = lib.NNG_TLS_AUTH_MODE_NONE
    AUTH_MODE_OPTIONAL = lib.NNG_TLS_AUTH_MODE_OPTIONAL
    AUTH_MODE_REQUIRED = lib.NNG_TLS_AUTH_MODE_REQUIRED

    _lib = lib
    _ffi = ffi


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

    _lib = lib
    _ffi = ffi
    _version_tag = "v2"

    def __init__(
        self,
        *,
        tls_config=None,
        listen=None,
        dial=None,
        block_on_dial=None,
        raw=False,
        **kwargs,
    ):
        self._tls_config = None
        if tls_config is not None:
            self.tls_config = tls_config
        super().__init__(
            listen=None,
            dial=None,
            block_on_dial=block_on_dial,
            raw=raw,
            **kwargs,
        )
        if listen is not None:
            self.listen(listen)
        if dial is not None:
            self.dial(dial, block=block_on_dial)

    @property
    def tls_config(self):
        """Default :class:`TLSConfig` for new endpoints whose transport has TLS."""
        return getattr(self, "_tls_config", None)

    @tls_config.setter
    def tls_config(self, value):
        if value is not None and not isinstance(value, _BaseTLSConfig):
            raise ValueError(
                f"Invalid value {value} of type {type(value)}.  Expected TLSConfig."
            )
        self._tls_config = value
        if value is not None:
            _retain_closed(value)

    def dial(self, address, *, block=None, tls_config=None, start=True):
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

    def _endpoint_tls(self, tls_config):
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
    def _set_endpoint_tls(set_tls, endpoint, tls_config, explicit):
        """Apply ``tls_config`` to an endpoint; return whether it was applied.

        The socket default is skipped on transports without TLS, which is what
        nng v1 does for a socket-level TLS config. An explicit config fails.
        """
        err = set_tls(endpoint, tls_config._config_for(lib, ffi))
        if err == lib.NNG_ENOTSUP and not explicit:
            return False
        check_err(err, lib=lib, ffi=ffi)
        return True

    def _dial(self, address, flags=0, *, tls_config=None, start=True):
        tls_config, explicit = self._endpoint_tls(tls_config)
        dialer = ffi.new("nng_dialer *")
        tls_applied = False
        if tls_config is not None or not start:
            check_err(
                lib.nng_dialer_create(
                    dialer, self.socket, to_char(address, ffi=ffi)
                ),
                lib=lib,
                ffi=ffi,
            )
            try:
                if tls_config is not None:
                    tls_applied = self._set_endpoint_tls(
                        lib.nng_dialer_set_tls, dialer[0], tls_config, explicit
                    )
                if start:
                    check_err(
                        lib.nng_dialer_start(dialer[0], flags), lib=lib, ffi=ffi
                    )
            except BaseException:
                lib.nng_dialer_close(dialer[0])
                raise
        else:
            check_err(
                lib.nng_dial(self.socket, to_char(address, ffi=ffi), dialer, flags),
                lib=lib,
                ffi=ffi,
            )
        d_id = lib.nng_dialer_id(dialer[0])
        dialer_cls = self._dialer_class or Dialer
        py_dialer = dialer_cls(dialer, self)
        if tls_applied:
            py_dialer._tls_config_ref = tls_config
            _retain_closed(tls_config)
        self._dialers[d_id] = py_dialer
        return py_dialer

    def listen(self, address, flags=0, *, tls_config=None, start=True):
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
        listener = ffi.new("nng_listener *")
        tls_applied = False
        if tls_config is not None or not start:
            check_err(
                lib.nng_listener_create(
                    listener, self.socket, to_char(address, ffi=ffi)
                ),
                lib=lib,
                ffi=ffi,
            )
            try:
                if tls_config is not None:
                    tls_applied = self._set_endpoint_tls(
                        lib.nng_listener_set_tls, listener[0], tls_config, explicit
                    )
                if start:
                    check_err(
                        lib.nng_listener_start(listener[0], flags), lib=lib, ffi=ffi
                    )
            except BaseException:
                lib.nng_listener_close(listener[0])
                raise
        else:
            check_err(
                lib.nng_listen(
                    self.socket, to_char(address, ffi=ffi), listener, flags
                ),
                lib=lib,
                ffi=ffi,
            )
        l_id = lib.nng_listener_id(listener[0])
        listener_cls = self._listener_class or Listener
        py_listener = listener_cls(listener, self)
        if tls_applied:
            py_listener._tls_config_ref = tls_config
            _retain_closed(tls_config)
        self._listeners[l_id] = py_listener
        return py_listener

    @property
    def _aio_recv_fn(self):
        """Return the v2 AIO receive function for socket-level operations."""
        return lib.nng_socket_recv

    @property
    def _aio_send_fn(self):
        """Return the v2 AIO send function for socket-level operations."""
        return lib.nng_socket_send

    @property
    def protocol(self):
        """The 16-bit protocol number for this socket (read-only)."""
        proto_id = ffi.new("uint16_t *")
        check_err(lib.nng_socket_proto_id(self.socket, proto_id))
        return proto_id[0]

    @property
    def protocol_name(self):
        """The protocol name for this socket (read-only)."""
        name_p = ffi.new("char **")
        check_err(lib.nng_socket_proto_name(self.socket, name_p))
        result = ffi.string(name_p[0]).decode()
        return result

    @property
    def peer(self):
        """The peer protocol id for this socket (read-only)."""
        peer_id = ffi.new("uint16_t *")
        check_err(lib.nng_socket_peer_id(self.socket, peer_id))
        return peer_id[0]

    @property
    def peer_name(self):
        """The peer protocol name for this socket (read-only)."""
        name_p = ffi.new("char **")
        check_err(lib.nng_socket_peer_name(self.socket, name_p))
        result = ffi.string(name_p[0]).decode()
        return result

    @property
    def raw(self):
        """Whether this socket is in raw mode (read-only)."""
        raw_p = ffi.new("bool *")
        check_err(lib.nng_socket_raw(self.socket, raw_p))
        return raw_p[0]

    @property
    def recv_fd(self):
        """The receive poll file descriptor for this socket (read-only)."""
        fd_p = ffi.new("int *")
        check_err(lib.nng_socket_get_recv_poll_fd(self.socket, fd_p))
        return fd_p[0]

    @property
    def send_fd(self):
        """The send poll file descriptor for this socket (read-only)."""
        fd_p = ffi.new("int *")
        check_err(lib.nng_socket_get_send_poll_fd(self.socket, fd_p))
        return fd_p[0]

    def close(self):
        """Close the socket, freeing all system resources.

        This method is idempotent and thread-safe. Uses ``nng_socket_close()``
        (the v2 API).

        A call from a pipe callback returns at once, and the socket finishes
        closing on another thread after the running pipe callbacks return.
        """
        self._do_close(lib.nng_socket_close)

    def recv(self, block=True):
        """Receive data on the socket.

        In v2, recv uses ``nng_recvmsg()`` since ``NNG_FLAG_ALLOC`` does not
        exist.

        Args:
            block: If True (default), blocks until data arrives or timeout.
                If False, returns immediately or raises ``pynng.TryAgain``.
        """
        msg = self.recv_msg(block=block)
        return msg.bytes

    def send(self, data, block=True):
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
        if isinstance(data, bytes):
            c_buf = data
        else:
            c_buf = ffi.from_buffer(data)
        err = lib.nng_send(self.socket, c_buf, len(data), flags)
        check_err(err)

    async def arecv(self):
        """Asynchronous version of :meth:`recv`."""
        msg = await self.arecv_msg()
        return msg.bytes

    async def asend(self, data):
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

    def stats(self):
        """Get snapshot of statistics for this socket."""
        return socket_stats(self)

    def stat(self, name):
        """Get a single statistic value by name for this socket."""
        return socket_stats(self)[name].value


class Bus0(Socket):
    """A v2 bus0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_bus0_open
    _raw_opener = lib.nng_bus0_open_raw


class Pair0(Socket):
    """A v2 pair0 socket for bidirectional one-to-one communication.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_pair0_open
    _raw_opener = lib.nng_pair0_open_raw


class Pair1(Socket):
    """A v2 pair1 socket for bidirectional communication.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.

    Accepts a ``polyamorous`` keyword argument. If True, uses
    ``nng_pair1_open_poly`` to allow multiple peers.
    """

    def __init__(self, *, polyamorous=False, raw=False, **kwargs):
        if raw:
            kwargs["opener"] = lib.nng_pair1_open_raw
        elif polyamorous:
            kwargs["opener"] = lib.nng_pair1_open_poly
        else:
            kwargs["opener"] = lib.nng_pair1_open
        super().__init__(raw=raw, **kwargs)

    polyamorous = BooleanOption("pair1:polyamorous")


class Push0(Socket):
    """A v2 push0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_push0_open
    _raw_opener = lib.nng_push0_open_raw


class Pull0(Socket):
    """A v2 pull0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_pull0_open
    _raw_opener = lib.nng_pull0_open_raw


class Pub0(Socket):
    """A v2 pub0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_pub0_open
    _raw_opener = lib.nng_pub0_open_raw


class Sub0(Socket):
    """A v2 sub0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.

    In v2, subscribe/unsubscribe uses dedicated functions
    (``nng_sub0_socket_subscribe``/``nng_sub0_socket_unsubscribe``)
    instead of option setters.
    """
    _opener = lib.nng_sub0_open
    _raw_opener = lib.nng_sub0_open_raw

    def __init__(self, *, topics=None, **kwargs):
        self._subscriptions = set()
        self._sub_lock = threading.RLock()
        self._init_topics = topics
        super().__init__(**kwargs)

    def _configure_protocol_options(self):
        topics = self._init_topics
        self._init_topics = None
        if topics is not None:
            if isinstance(topics, (str, bytes)):
                topics = [topics]
            for topic in topics:
                self.subscribe(topic)

    @property
    def subscriptions(self):
        """Return a frozenset of current subscriptions (as bytes)."""
        with self._sub_lock:
            return frozenset(self._subscriptions)

    def subscribe(self, topic):
        """Subscribe to the specified topic.

        Uses the v2 dedicated function ``nng_sub0_socket_subscribe()``.

        Args:
            topic: str or bytes topic to subscribe to. Strings are
                automatically encoded to bytes.
        """
        if isinstance(topic, str):
            topic = topic.encode()
        check_err(lib.nng_sub0_socket_subscribe(self.socket, topic, len(topic)))
        with self._sub_lock:
            self._subscriptions.add(topic)

    def unsubscribe(self, topic):
        """Unsubscribe from the specified topic.

        Uses the v2 dedicated function ``nng_sub0_socket_unsubscribe()``.

        Args:
            topic: str or bytes topic to unsubscribe from. Strings are
                automatically encoded to bytes.
        """
        if isinstance(topic, str):
            topic = topic.encode()
        check_err(lib.nng_sub0_socket_unsubscribe(self.socket, topic, len(topic)))
        with self._sub_lock:
            self._subscriptions.discard(topic)

    def subscribe_all(self, topics):
        """Subscribe to multiple topics at once.

        Args:
            topics: An iterable of :class:`str` or :class:`bytes` topics.
        """
        for topic in topics:
            self.subscribe(topic)

    def unsubscribe_all(self):
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
    _opener = lib.nng_req0_open
    _raw_opener = lib.nng_req0_open_raw

    def __init__(self, *, resend_time=None, **kwargs):
        super().__init__(**kwargs)
        if resend_time is not None:
            self.resend_time = resend_time


class Rep0(Socket):
    """A v2 rep0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_rep0_open
    _raw_opener = lib.nng_rep0_open_raw


class Surveyor0(Socket):
    """A v2 surveyor0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_surveyor0_open
    _raw_opener = lib.nng_surveyor0_open_raw
    _nonblock_recv_first = False
    survey_time = MsOption("surveyor:survey-time")

    def __init__(self, *, survey_time=None, **kwargs):
        super().__init__(**kwargs)
        if survey_time is not None:
            self.survey_time = survey_time

    async def asurvey(self, data, *, timeout=None, max_responses=None):
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
            responses = []
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
    _opener = lib.nng_respondent0_open
    _raw_opener = lib.nng_respondent0_open_raw


class RawBus0(Bus0):
    """A raw v2 bus0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawPair0(Pair0):
    """A raw v2 pair0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawPair1(Pair1):
    """A raw v2 pair1 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawPush0(Push0):
    """A raw v2 push0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawPull0(Pull0):
    """A raw v2 pull0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawPub0(Pub0):
    """A raw v2 pub0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawSub0(Sub0):
    """A raw v2 sub0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawReq0(Req0):
    """A raw v2 req0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawRep0(Rep0):
    """A raw v2 rep0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawSurveyor0(Surveyor0):
    """A raw v2 surveyor0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


class RawRespondent0(Respondent0):
    """A raw v2 respondent0 socket."""

    def __init__(self, **kwargs):
        kwargs.setdefault("raw", True)
        super().__init__(**kwargs)


def _url_string(urlp):
    """Format an ``nng_url *`` with ``nng_url_sprintf``."""
    size = lib.nng_url_sprintf(ffi.NULL, 0, urlp) + 1
    buf = ffi.new("char[]", size)
    lib.nng_url_sprintf(buf, size, urlp)
    return ffi.string(buf).decode()


class Dialer(_base.Dialer):
    """v2 dialer. Supports TLS configuration at the endpoint level.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    @property
    def url(self):
        """The URL string for this dialer."""
        urlp = ffi.new("struct nng_url **")
        check_err(lib.nng_dialer_get_url(self.dialer, urlp), lib=lib, ffi=ffi)
        return _url_string(urlp[0])

    @property
    def tls_config(self):
        """The :class:`TLSConfig` applied to this dialer, or None.

        None also when the dialer uses TLS with nng's default configuration.
        """
        return getattr(self, "_tls_config_ref", None)

    @tls_config.setter
    def tls_config(self, value):
        if not isinstance(value, _BaseTLSConfig):
            raise ValueError(
                f"Invalid value {value} of type {type(value)}.  Expected TLSConfig."
            )
        check_err(
            lib.nng_dialer_set_tls(self.dialer, value._config_for(lib, ffi)),
            lib=lib,
            ffi=ffi,
        )
        self._tls_config_ref = value
        _retain_closed(value)

    def start(self, *, block=True):
        """Start a dialer created with ``dial(..., start=False)``."""
        flags = 0 if block else lib.NNG_FLAG_NONBLOCK
        check_err(lib.nng_dialer_start(self.dialer, flags), lib=lib, ffi=ffi)

    @property
    def local_address(self):
        """Local address for this dialer, if a connected pipe exists."""
        for pipe in self.socket.pipes:
            try:
                if pipe.dialer == self:
                    return pipe.local_address
            except (TypeError, KeyError):
                continue
        return None

    @property
    def remote_address(self):
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

    @property
    def url(self):
        """The URL string for this listener.

        After the listener starts, a TCP-based URL has the port that was bound,
        also when the URL asked for port 0.
        """
        urlp = ffi.new("struct nng_url **")
        check_err(lib.nng_listener_get_url(self.listener, urlp), lib=lib, ffi=ffi)
        return _url_string(urlp[0])

    @property
    def tls_config(self):
        """The :class:`TLSConfig` applied to this listener, or None.

        None also when the listener uses TLS with nng's default configuration.
        """
        return getattr(self, "_tls_config_ref", None)

    @tls_config.setter
    def tls_config(self, value):
        if not isinstance(value, _BaseTLSConfig):
            raise ValueError(
                f"Invalid value {value} of type {type(value)}.  Expected TLSConfig."
            )
        check_err(
            lib.nng_listener_set_tls(self.listener, value._config_for(lib, ffi)),
            lib=lib,
            ffi=ffi,
        )
        self._tls_config_ref = value
        _retain_closed(value)

    def start(self, flags=0):
        """Start a listener created with ``listen(..., start=False)``."""
        check_err(lib.nng_listener_start(self.listener, flags), lib=lib, ffi=ffi)

    @property
    def local_address(self):
        """Local address for this listener, if a connected pipe exists."""
        for pipe in self.socket.pipes:
            try:
                if pipe.listener == self:
                    return pipe.local_address
            except (TypeError, KeyError):
                continue
        return None

    @property
    def remote_address(self):
        """Remote address for this listener (not applicable)."""
        return None


class Context(_base.Context):
    """v2 context for multiplexing protocol state on a single socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    pass


class Pipe(_base.Pipe):
    """v2 pipe representing a single connection between two endpoints.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    @property
    def local_address(self):
        """The local address for this pipe."""
        sa = ffi.new("nng_sockaddr *")
        check_err(lib.nng_pipe_self_addr(self.pipe, sa))
        return pynng.sockaddr._nng_sockaddr(sa, lib=lib)

    @property
    def remote_address(self):
        """The remote address for this pipe."""
        sa = ffi.new("nng_sockaddr *")
        check_err(lib.nng_pipe_peer_addr(self.pipe, sa))
        return pynng.sockaddr._nng_sockaddr(sa, lib=lib)

    @property
    def scheme(self):
        """The transport scheme for this pipe (e.g. 'tcp', 'ipc')."""
        scheme_p = ffi.new("char **")
        check_err(lib.nng_pipe_get_scheme(self.pipe, scheme_p))
        return ffi.string(scheme_p[0]).decode()



class Message(_base.Message):
    """v2 message.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

    __slots__ = ()
    _lib = lib
    _ffi = ffi

    def __init__(self, data=b"", pipe=None, *, _lib=None, _ffi=None):
        super().__init__(data, pipe, _lib=_lib or lib, _ffi=_ffi or ffi)


class Rep0Service(_service_mod.Rep0Service):
    """High-level async REP service backed by a v2 :class:`Rep0` socket.

    The same as :class:`pynng.Rep0Service`, but a ``socket`` argument must be
    a :class:`pynng.v2.Rep0`.
    """

    _socket_class = Rep0


def stats():
    """Retrieve a snapshot of all v2 runtime statistics in the process."""
    return _stats(lib, ffi)


def socket_stats(sock):
    """Retrieve statistics for a v2 socket.

    Args:
        sock: A v2 :class:`Socket` or a v2 ``nng_socket`` handle.

    Returns:
        Stat: The socket's stat subtree, or None if not found.
    """
    return _socket_stats(sock, lib, ffi)


def device(s1, s2=None):
    """Forward messages between v2 sockets; see :func:`pynng.device`.

    Closing either socket ends the device with :class:`Closed`. nng v2 gives
    the device both sockets, so when the device ends, nng closes both.
    """
    _device(s1, s2, lib, ffi)


async def adevice(s1, s2=None, *, async_backend=None):
    """Asynchronous version of :func:`device`; see :func:`pynng.adevice`."""
    await _adevice(s1, s2, async_backend, lib, ffi)


# Wire up v2-specific subclasses so base class factory methods
# create v2 types instead of _base types.
Socket._context_class = Context
Socket._pipe_class = Pipe
Socket._dialer_class = Dialer
Socket._listener_class = Listener
Socket._message_class = Message
