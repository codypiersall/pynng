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
from pynng.exceptions import check_err, Closed
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


logger = logging.getLogger(__name__)


class Socket(_base.Socket):
    """v2 socket base class.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.

    v2 sockets differ from v1 in several ways:

    - ``close()`` uses ``nng_socket_close()`` instead of ``nng_close()``
    - ``recv()`` uses ``nng_recvmsg()`` (no ``NNG_FLAG_ALLOC`` in v2)
    - Protocol/peer info uses dedicated functions instead of option accessors
    - No ``name`` property (``NNG_OPT_SOCKNAME`` removed in v2)
    - TLS configuration is per-endpoint, not per-socket
    """

    _lib = lib
    _ffi = ffi
    _version_tag = "v2"

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


class Bus0(Socket):
    """A v2 bus0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_bus0_open


class Pair0(Socket):
    """A v2 pair0 socket for bidirectional one-to-one communication.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_pair0_open


class Pair1(Socket):
    """A v2 pair1 socket for bidirectional communication.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.

    Accepts a ``polyamorous`` keyword argument. If True, uses
    ``nng_pair1_open_poly`` to allow multiple peers.
    """

    def __init__(self, *, polyamorous=False, **kwargs):
        if polyamorous:
            kwargs["opener"] = lib.nng_pair1_open_poly
        else:
            kwargs["opener"] = lib.nng_pair1_open
        super().__init__(**kwargs)

    polyamorous = BooleanOption("pair1:polyamorous")


class Push0(Socket):
    """A v2 push0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_push0_open


class Pull0(Socket):
    """A v2 pull0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_pull0_open


class Pub0(Socket):
    """A v2 pub0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_pub0_open


class Sub0(Socket):
    """A v2 sub0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.

    In v2, subscribe/unsubscribe uses dedicated functions
    (``nng_sub0_socket_subscribe``/``nng_sub0_socket_unsubscribe``)
    instead of option setters.
    """
    _opener = lib.nng_sub0_open

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

    def __init__(self, *, resend_time=None, **kwargs):
        super().__init__(**kwargs)
        if resend_time is not None:
            self.resend_time = resend_time


class Rep0(Socket):
    """A v2 rep0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_rep0_open


class Surveyor0(Socket):
    """A v2 surveyor0 socket.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """
    _opener = lib.nng_surveyor0_open
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


class Dialer(_base.Dialer):
    """v2 dialer. Supports TLS configuration at the endpoint level.

    .. warning:: nng v2 is experimental/alpha. The API may change between releases.
    """

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
        return pynng.sockaddr._nng_sockaddr(sa)

    @property
    def remote_address(self):
        """The remote address for this pipe."""
        sa = ffi.new("nng_sockaddr *")
        check_err(lib.nng_pipe_peer_addr(self.pipe, sa))
        return pynng.sockaddr._nng_sockaddr(sa)

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


# Wire up v2-specific subclasses so base class factory methods
# create v2 types instead of _base types.
Socket._context_class = Context
Socket._pipe_class = Pipe
Socket._dialer_class = Dialer
Socket._listener_class = Listener
Socket._message_class = Message
