"""
Provides a Pythonic interface to cffi nng bindings
"""

from __future__ import annotations

import atexit
from collections.abc import Callable, Iterable
import logging
import threading
from typing import TYPE_CHECKING, ClassVar, Protocol, TypeVar, cast

import pynng  # noqa: F401

from . import _aio, _base, options
from ._base import (  # noqa: F401
    BooleanOption,
    IntOption,
    MsOption,
    NotImplementedOption,
    PipeEvent,
    PipeEventStream,
    PointerOption,
    ReadOnlyBooleanOption,
    ReadOnlyIntOption,
    ReadOnlyStringOption,
    SizeOption,
    SockAddrOption,
    StringOption,
    _active_handles,
    _ensure_can_send,
    _NNGOption,
    _ReadOnlyOption,
    to_char,
)
from ._nng import ffi, lib
from .exceptions import (  # noqa: F401
    BadState,
    Closed,
    NNGException,
    NoEntry,
    Timeout,
    check_err,
)
from .stats import Stat, socket_stats, stats

if TYPE_CHECKING:
    import cffi

    from . import _nng
    from .tls import TLSConfig  # noqa: F401

logger = logging.getLogger(__name__)

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
    "Req0",
    "Respondent0",
    "Socket",
    "Stat",
    "Sub0",
    "Surveyor0",
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
    """Explicitly finalize the NNG library runtime.

    Frees global NNG resources. After calling this function, no further NNG
    operations should be performed; remaining Python objects skip C deallocations
    during GC.
    """
    global _finalized
    if not _finalized:
        _finalized = True
        lib.nng_fini()


def _pynng_atexit() -> None:
    if nng_fini_at_exit:
        nng_fini()


atexit.register(_pynng_atexit)


class Socket(_base.Socket):
    """
    Open a socket with one of the scalability protocols.  This should not be
    instantiated directly; instead, one of its subclasses should be used.
    There is one subclass per protocol.  The available protocols are:

        * :class:`Pair0`
        * :class:`Pair1`
        * :class:`Req0` / :class:`Rep0`
        * :class:`Pub0` / :class:`Sub0`
        * :class:`Push0` / :class:`Pull0`
        * :class:`Surveyor0` / :class:`Respondent0`
        * :class:`Bus0`

    The socket initializer receives no positional arguments.  It accepts the
    following keyword arguments, with the same meaning as the :ref:`attributes
    <socket-attributes>` described below: ``recv_timeout``, ``send_timeout``,
    ``recv_buffer_size``, ``send_buffer_size``, ``reconnect_time_min``,
    ``reconnect_time_max``, and ``name``

    To talk to another socket, you have to either :meth:`~Socket.dial`
    its address, or :meth:`~Socket.listen` for connections.  Then you can
    :meth:`~Socket.send` to send data to the remote sockets or
    :meth:`~Socket.recv` to receive data from the remote sockets.
    Asynchronous versions are available as well, as :meth:`~Socket.asend`
    and :meth:`~Socket.arecv`.  The supported event loops are :mod:`asyncio`
    and `Trio`_.  You must ensure that you :meth:`~Socket.close` the socket
    when you are finished with it.  Sockets can also be used as a context
    manager; this is the preferred way to use them when possible.

    .. _socket-attributes:

    Sockets have the following attributes.  Generally, you should set these
    attributes before :meth:`~Socket.listen`-ing or
    :meth:`~Socket.dial`-ing, or by passing them in as keyword arguments
    when creating the :class:`Socket`:

        * **recv_timeout** (int): Receive timeout, in ms.  If a socket takes longer
          than the specified time, raises a ``pynng.exceptions.Timeout``.
          Corresponds to library option ``NNG_OPT_RECVTIMEO``
        * **send_timeout** (int): Send timeout, in ms.  If the message cannot
          be queued in the specified time, raises a pynng.exceptions.Timeout.
          Corresponds to library option ``NNG_OPT_SENDTIMEO``.
        * **recv_max_size** (int): The largest size of a message to receive.
          Messages larger than this size will be silently dropped.  A size of 0
          indicates unlimited size.  The default size is 1 MB.
        * **recv_buffer_size** (int): The number of messages that the socket
          will buffer on receive. Default is 128. For pub/sub sockets, messages
          exceeding this limit are dropped; for other protocols, backpressure is applied.
        * **send_buffer_size** (int): The number of messages that the socket
          will buffer on send. Default is 128. For pub/sub sockets, messages
          exceeding this limit are dropped; for other protocols, senders block or yield.
        * **name** (str): The socket name.  Corresponds to
          ``NNG_OPT_SOCKNAME``.  This is useful for debugging purposes.
        * **raw** (bool): A boolean, indicating whether the socket is raw or cooked.
          Returns ``True`` if the socket is raw, else ``False``.  This property
          is read-only.  Corresponds to library option ``NNG_OPT_RAW``.  For
          more information see `nng's documentation.
          <https://nanomsg.github.io/nng/man/v1.0.1/nng.7.html#raw_mode>`_
          Note that currently, pynng does not support ``raw`` mode sockets, but
          we intend to `in the future
          <https://github.com/codypiersall/pynng/issues/35>`_:
        * **protocol** (int): Read-only option which returns the 16-bit number
          of the socket's protocol.
        * **protocol_name** (str): Read-only option which returns the name of the
          socket's protocol.
        * **peer** (int): Returns the peer protocol id for the socket.
        * **reconnect_time_min** (int): The minimum time to wait before
          attempting reconnects, in ms.  Corresponds to ``NNG_OPT_RECONNMINT``.
          This can also be overridden on the dialers.
        * **reconnect_time_max** (int): The maximum time to wait before
          attempting reconnects, in ms.  Corresponds to ``NNG_OPT_RECONNMAXT``.
          If this is non-zero, then the time between successive connection
          attempts will start at the value of ``reconnect_time_min``, and grow
          exponentially, until it reaches this value.  This option can be set
          on the socket, or on the dialers associated with the socket.
        * **recv_fd** (int): The receive file descriptor associated with the
          socket.  This is suitable to be passed into poll functions like
          :func:`select.poll` or :func:`select.select`.  That is the only thing
          this file descriptor is good for; do not attempt to read from or
          write to it.  The file descriptor will be marked as **readable**
          whenever it can receive data without blocking.  Corresponds to
          ``NNG_OPT_RECVFD``.
        * **send_fd** (int): The sending file descriptor associated with the
          socket.  This is suitable to be passed into poll functions like
          :func:`select.poll` or :func:`select.select`.  That is the only thing
          this file descriptor is good for; do not attempt to read from or
          write to it.  The file descriptor will be marked as **readable**
          whenever it can send data without blocking.  Corresponds to
          ``NNG_OPT_SENDFD``.

         .. Note::

             When used in :func:`select.poll` or :func:`select.select`,
             ``recv_fd`` and ``send_fd`` are both marked as **readable** when
             they can receive or send data without blocking.  So the upshot is
             that for :func:`select.select` they should be passed in as the
             *rlist* and for :meth:`select.poll.register` the *eventmask*
             should be ``POLLIN``.

        * **tls_config** (:class:`~pynng.TLSConfig`): The TLS configuration for
          this socket.  This option is only valid if the socket is using the
          TLS transport.  See :class:`~pynng.TLSConfig` for information about
          the TLS configuration.  Corresponds to ``NNG_OPT_TLS_CONFIG``.  This
          option is write-only.

    .. _Trio: https://trio.readthedocs.io

    """

    # Set v1 CFFI lib and ffi
    _lib: ClassVar[_base._NngLib] = lib
    _ffi: ClassVar[cffi.FFI] = ffi
    _version_tag = "v1"

    # v1-specific options (not in base class)
    name = StringOption("socket-name")
    raw = ReadOnlyBooleanOption("raw")
    protocol = ReadOnlyIntOption("protocol")
    protocol_name = ReadOnlyStringOption("protocol-name")
    peer = ReadOnlyIntOption("peer")
    peer_name = ReadOnlyStringOption("peer-name")
    recv_fd = ReadOnlyIntOption("recv-fd")
    send_fd = ReadOnlyIntOption("send-fd")

    tls_config = PointerOption("tls-config")

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
    ) -> None:
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
        if tls_config is not None:
            self.tls_config = tls_config
        if name is not None:
            self.name = name
        if listen is not None:
            self.listen(listen)
        if dial is not None:
            self.dial(dial, block=block_on_dial)

    def close(self) -> None:
        """Close the socket, freeing all system resources.

        This method is idempotent and thread-safe. It may be called multiple
        times (e.g. via __exit__ and later __del__) without harm.

        A call from a pipe callback returns at once, and the socket finishes
        closing on another thread after the running pipe callbacks return.
        """
        self._do_close(lib.nng_close)

    def recv(self, block: bool = True) -> bytes:
        """Receive data on the socket.  If the request times out the exception
        :class:`pynng.Timeout` is raised.  If the socket cannot perform that
        operation (e.g., a :class:`Pub0`, which can only
        :meth:`~Socket.send`), the exception :class:`pynng.NotSupported`
        is raised.

        Args:

          block: If block is True (the default), the function will not return
            until the operation is completed or times out.  If block is False,
            the function will return data immediately.  If no data is ready on
            the socket, the function will raise ``pynng.TryAgain``.

        """
        msg = self.recv_msg(block=block)
        return msg.bytes

    def send(self, data: _base.ReadableBuffer, block: bool = True) -> None:
        """Sends ``data`` on socket.

        Args:

          data: bytes, bytearray, memoryview, or any buffer-protocol object.

          block: If block is True (the default), the function will
            not return until the operation is completed or times out.
            If block is False, the function will raise ``pynng.TryAgain``
            immediately if no data was sent (such as when the send buffer is full).

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
        err = lib.nng_send(self.socket, c_buf, len(data), flags)
        check_err(err)

    async def arecv(self) -> bytes:
        """The asynchronous version of :meth:`~Socket.recv`"""
        msg = await self.arecv_msg()
        return msg.bytes

    async def asend(self, data: _base.ReadableBuffer) -> None:
        """Asynchronous version of :meth:`~Socket.send`.

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
        def socket(self) -> _nng.nng_socket: ...

        def dial(
            self, address: str | bytes, *, block: bool | None = None
        ) -> Dialer: ...

        def listen(self, address: str | bytes, flags: int = 0) -> Listener: ...

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


class Bus0(Socket):
    """A bus0 socket.  The Python version of `nng_bus
    <https://nanomsg.github.io/nng/man/tip/nng_bus.7>`_.

    It accepts the same keyword arguments as :class:`Socket` and also has the
    same :ref:`attributes <socket-attributes>`.

    A :class:`Bus0` socket sends a message to all directly connected peers.
    This enables creating mesh networks.  Note that messages are only sent to
    *directly* connected peers.  You must explicitly connect all nodes with the
    :meth:`~Socket.listen` and corresponding :meth:`~Socket.listen` calls.

    Here is a demonstration of using the bus protocol:

    .. literalinclude:: /snippets/bus0_sync.py
        :language: python3
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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class Pair0(Socket):
    """A socket for bidrectional, one-to-one communication, with a single
    partner.  The Python version of `nng_pair0
    <https://nanomsg.github.io/nng/man/tip/nng_pair.7>`_.

    This is the most basic type of socket.
    It accepts the same keyword arguments as :class:`Socket` and also has the
    same :ref:`attributes <socket-attributes>`.

    This demonstrates the synchronous API:

    .. literalinclude:: /snippets/pair0_sync.py
        :language: python3

    This demonstrates the asynchronous API using `Trio`_.  Remember that
    :mod:`asyncio` is also supported.

    .. literalinclude:: /snippets/pair0_async.py
        :language: python3


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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class Pair1(Socket):
    """A socket for bidrectional communication with potentially many peers.
    The Python version of `nng_pair1
    <https://nanomsg.github.io/nng/man/tip/nng_pair.7>`_.

    It accepts the same keyword arguments as :class:`Socket` and also has the
    same :ref:`attributes <socket-attributes>`.  It also has one extra
    keyword-only argument, ``polyamorous``, which must be set to ``True`` to
    connect with more than one peer.

    .. Warning::

        If you want to connect to multiple peers you **must** pass
        ``polyamorous=True`` when you create your socket.  ``polyamorous`` is a
        read-only attribute of the socket and cannot be changed after creation.

    .. Warning::

        Polyamorous mode was an experimental feature in nng, and is currently
        deprecated. It will likely be removed in the future; see `nng's docs
        <https://nng.nanomsg.org/man/v1.3.2/nng_pair_open.3.html>`_ for
        details.

    To get the benefits of polyamory, you need to use the methods that work
    with :class:`Message` objects: :meth:`Socket.recv_msg` and
    :meth:`Socket.arecv_msg` for receiving, and :meth:`Pipe.send`
    and :meth:`Pipe.asend` for sending.

    Here is an example of the synchronous API, where a single listener connects
    to multiple peers.  This is more complex than the :class:`Pair0` case,
    because it requires to use the :class:`Pipe` and :class:`Message`
    interfaces.

    .. literalinclude:: /snippets/pair1_sync.py

    And here is an example using the async API, using `Trio`_.

    .. literalinclude:: /snippets/pair1_async.py

    """

    _raw_opener: _base._OpenerFn | None = lib.nng_pair1_open_raw

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )

    polyamorous = BooleanOption("pair1:polyamorous")


class Push0(Socket):
    """A push0 socket.

    The Python version of `nng_push
    <https://nanomsg.github.io/nng/man/tip/nng_push.7>`_.
    It accepts the same keyword arguments as :class:`Socket` and also
    has the same :ref:`attributes <socket-attributes>`.

    A :class:`Push0` socket is the pushing end of a data pipeline.  Data sent
    from a push socket will be sent to a *single* connected :class:`Pull0`
    socket.  This can be useful for distributing work to multiple nodes, for
    example.  Attempting to call :meth:`~Socket.recv()` on a Push0 socket
    will raise a :class:`pynng.NotSupported` exception.

    Here is an example of two :class:`Pull0` sockets connected to a
    :class:`Push0` socket.

    .. literalinclude:: /snippets/pushpull_sync.py

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class Pull0(Socket):
    """A pull0 socket.

    The Python version of `nng_pull
    <https://nanomsg.github.io/nng/man/tip/nng_pull.7>`_.
    It accepts the same keyword arguments as :class:`Socket` and also
    has the same :ref:`attributes <socket-attributes>`.

    A :class:`Pull0` is the receiving end of a data pipeline.  It needs to be
    paired with a :class:`Push0` socket.
    Attempting to :meth:`~Socket.send()`
    with a Pull0 socket will raise a :class:`pynng.NotSupported` exception.

    See :class:`Push0` for an example of push/pull in action.

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class Pub0(Socket):
    """A pub0 socket.

    The Python version of `nng_pub
    <https://nanomsg.github.io/nng/man/tip/nng_pub.7>`_.
    It accepts the same keyword arguments as :class:`Socket` and also has the
    same :ref:`attributes <socket-attributes>`.  A :class:`Pub0` socket calls
    :meth:`~Socket.send`, the data is published to all connected
    :class:`subscribers <Sub0>`.

    Attempting to :meth:`~Socket.recv` with a Pub0 socket will raise a
    :class:`pynng.NotSupported` exception.

    .. note::

        Pub/Sub is a lossy, best-effort transport. If subscribers or network
        pipes cannot keep pace with publications, messages exceeding
        :attr:`~Socket.send_buffer_size` (default 128 messages) are silently
        dropped to protect against producer stalling. Increase ``send_buffer_size``
        (e.g., 512, 1024) to absorb bursty publication rates.

    See docs for :class:`Sub0` for an example.

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class Sub0(Socket):
    """A sub0 socket.

    The Python version of `nng_sub
    <https://nanomsg.github.io/nng/man/tip/nng_sub.7>`_.
    It accepts the same keyword arguments as :class:`Socket` and also
    has the same :ref:`attributes <socket-attributes>`.  It also has one
    additional keyword argument: ``topics``.  If ``topics`` is given, it must
    be either a :class:`str`, :class:`bytes`, or an iterable of str and bytes.

    A subscriber must :meth:`~Sub0.subscribe` to specific topics, and only
    messages that match the topic will be received.  A subscriber can subscribe
    to as many topics as you want it to.

    A match is determined if the message starts with one of the subscribed
    topics.  So if the subscribing socket is subscribed to the topic
    ``b'hel'``, then the messages ``b'hel'``, ``b'help him`` and ``b'hello'``
    would match, but the message ``b'hexagon'`` would not.  Subscribing to an
    empty string (``b''``) means that all messages will match.  If a sub socket
    is not subscribed to any topics, no messages will be receieved.

    .. note::

        Pub/Sub is a lossy, best-effort transport. If the subscriber's receive
        loop falls behind incoming traffic, messages exceeding
        :attr:`~Socket.recv_buffer_size` (default 128 messages) will be
        silently dropped. Increase ``recv_buffer_size`` (e.g., 512, 1024) to
        absorb spikes, and ensure the receive coroutine drains promptly.

    Attempting to :meth:`~Socket.send` with a Sub0 socket will raise a
    :class:`pynng.NotSupported` exception.

    The following example demonstrates a basic usage of pub/sub:

    .. literalinclude:: /snippets/pubsub_sync.py

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )

    def _configure_protocol_options(self) -> None:
        topics = self._init_topics
        self._init_topics = None
        if topics is not None:
            # special-case str/bytes
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

        Topics are matched by looking at the first bytes of any received
        message.

        .. Note::

            If you pass a :class:`str` as the ``topic``, it will be
            automatically encoded with :meth:`str.encode`.  If this is not the
            desired behavior, just pass :class:`bytes` in as the topic.

        """
        if isinstance(topic, str):
            topic = topic.encode()
        options._setopt_string_nonnull(self, b"sub:subscribe", topic)
        with self._sub_lock:
            self._subscriptions.add(topic)

    def unsubscribe(self, topic: str | bytes) -> None:
        """Unsubscribe from the specified topic.

        .. Note::

            If you pass a :class:`str` as the ``topic``, it will be
            automatically encoded with :meth:`str.encode`.  If this is not the
            desired behavior, just pass :class:`bytes` in as the topic.

        """
        if isinstance(topic, str):
            topic = topic.encode()
        options._setopt_string_nonnull(self, b"sub:unsubscribe", topic)
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
                try:
                    self.unsubscribe(topic)
                except NoEntry:
                    pass


class Req0(Socket):
    """A req0 socket.

    The Python version of `nng_req
    <https://nanomsg.github.io/nng/man/tip/nng_req.7>`_.
    It accepts the same keyword arguments as :class:`Socket` and also
    has the same :ref:`attributes <socket-attributes>`.  It also has one extra
    keyword-argument: ``resend_time``.  ``resend_time`` corresponds to
    ``NNG_OPT_REQ_RESENDTIME``

    A :class:`Req0` socket is paired with a :class:`Rep0` socket and together
    they implement normal request/response behavior.  the req socket
    :meth:`send()s <Socket.send>` a request, the rep socket :meth:`recv()s
    <Socket.recv>` it, the rep socket :meth:`send()s <Socket.Send>` a response,
    and the req socket :meth:`recv()s <Socket.recv>` it.

    If a req socket attempts to do a :meth:`~Socket.recv` without first doing a
    :meth:`~Socket.send`, a :class:`pynng.BadState` exception is raised.

    A :class:`Req0` socket supports opening multiple :class:`Contexts
    <Context>` by calling :meth:`~Socket.new_context`.  In this way a req
    socket can have multiple outstanding requests to a single rep socket.
    Without opening a :class:`Context`, the socket can only have a single
    outstanding request at a time.

    Here is an example demonstrating the request/response pattern.

    .. literalinclude:: /snippets/reqrep_sync.py

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )
        if resend_time is not None:
            self.resend_time = resend_time


class Rep0(Socket):
    """A rep0 socket.

    The Python version of `nng_rep
    <https://nanomsg.github.io/nng/man/tip/nng_rep.7>`_.
    It accepts the same keyword arguments as :class:`Socket` and also
    has the same :ref:`attributes <socket-attributes>`.

    A :class:`Rep0` socket along with a :class:`Req0` socket implement the
    request/response pattern:
    the req socket :meth:`send()s <Socket.send>` a
    request, the rep socket :meth:`recv()s <Socket.recv>` it, the rep socket
    :meth:`send()s <Socket.Send>` a response, and the req socket :meth:`recv()s
    <Socket.recv>` it.

    A :class:`Rep0` socket supports opening multiple :class:`Contexts
    <Context>` by calling :meth:`~Socket.new_context`.  In this way a rep
    socket can service multiple requests at the same time.  Without opening a
    :class:`Context`, the rep socket can only service a single request at a
    time.

    See the documentation for :class:`Req0` for an example.

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class Surveyor0(Socket):
    """A surveyor0 socket.

    The Python version of `nng_surveyor
    <https://nanomsg.github.io/nng/man/tip/nng_surveyor.7>`_.
    It accepts the same keyword arguments as :class:`Socket` and also
    has the same :ref:`attributes <socket-attributes>`.  It has one additional
    attribute: ``survey_time``.  ``survey_time`` sets the amount of time a
    survey lasts.

    :class:`Surveyor0` sockets work with :class:`Respondent0` sockets in the
    survey pattern.  In this pattern, a :class:`surveyor <Surveyor0>` sends a
    message, and gives all :class:`respondents <Respondent0>` a chance to
    chime in.  The amount of time a survey is valid is set by the attribute
    ``survey_time``.  ``survey_time`` is the time of a survey in milliseconds.

    Here is an example:

    .. literalinclude:: /snippets/surveyor_sync.py

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
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
            max_responses: Maximum number of responses to collect. If
                None (the default), collects all responses until timeout.
                Useful for bounding memory usage when the number of
                respondents is unknown.

        Returns:
            list[bytes]: All responses received before timeout or
            max_responses limit.

        Note:
            The survey protocol does not support nng contexts, so when a
            ``timeout`` is provided this method temporarily modifies the
            socket-level ``recv_timeout``. A try/finally block ensures the
            original value is restored, but callers sharing the socket
            across concurrent tasks should be aware this is not task-safe.
            If task-safety is required, use a dedicated socket per task.
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

    def recv_msg(self, block: bool = True) -> Message:
        """Receive a message on the surveyor socket, translating survey expiration to Timeout."""
        try:
            msg = super().recv_msg(block=block)
            assert isinstance(msg, Message)
            return msg
        except BadState:
            raise Timeout("Timed out", 5)


class Respondent0(Socket):
    """A respondent0 socket.

    The Python version of `nng_respondent
    <https://nanomsg.github.io/nng/man/tip/nng_respondent.7>`_.
    It accepts the same keyword arguments as :class:`Socket` and also
    has the same :ref:`attributes <socket-attributes>`.  It accepts no
    additional arguments and has no other attributes

    :class:`Surveyor0` sockets work with :class:`Respondent0` sockets in the
    survey pattern.  In this pattern, a :class:`surveyor <Surveyor0>` sends a
    message, and gives all :class:`respondents <Respondent0>` a chance to
    chime in.  The amount of time a survey is valid is set by the attribute
    ``survey_time``.  ``survey_time`` is the time of a survey in milliseconds.

    See :class:`Surveyor0` docs for an example.

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawBus0(Bus0):
    """A raw bus0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawPair0(Pair0):
    """A raw pair0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawPair1(Pair1):
    """A raw pair1 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawPush0(Push0):
    """A raw push0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawPull0(Pull0):
    """A raw pull0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawPub0(Pub0):
    """A raw pub0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawSub0(Sub0):
    """A raw sub0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawReq0(Req0):
    """A raw req0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawRep0(Rep0):
    """A raw rep0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawSurveyor0(Surveyor0):
    """A raw surveyor0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class RawRespondent0(Respondent0):
    """A raw respondent0 socket."""

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
        name: str | bytes | None = None,
        tls_config: TLSConfig | None = None,
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
            name=name,
            tls_config=tls_config,
        )


class Dialer(_base.Dialer):
    """The Python version of `nng_dialer
    <https://nanomsg.github.io/nng/man/tip/nng_dialer.5>`_.  A
    :class:`Dialer` is returned whenever :meth:`Socket.dial` is called.  A list
    of active dialers can be accessed via ``Socket.dialers``.

    A :class:`Dialer` is associated with a single :class:`Socket`.  The
    associated socket can be accessed via the ``socket`` attribute.  There is
    no public constructor for creating a :class:`Dialer`

    """

    local_address = SockAddrOption("local-address")
    remote_address = SockAddrOption("remote-address")
    reconnect_time_min = MsOption("reconnect-time-min")
    reconnect_time_max = MsOption("reconnect-time-max")
    recv_max_size = SizeOption("recv-size-max")
    url = ReadOnlyStringOption("url")
    peer = ReadOnlyIntOption("peer")
    peer_name = ReadOnlyStringOption("peer-name")
    tcp_nodelay = BooleanOption("tcp-nodelay")
    tcp_keepalive = BooleanOption("tcp-keepalive")

    # v1-specific TLS options on the dialer
    tls_config = PointerOption("tls-config")
    tls_ca_file = StringOption("tls-ca-file")
    tls_cert_key_file = StringOption("tls-cert-key-file")
    tls_auth_mode = IntOption("tls-authmode")
    tls_server_name = StringOption("tls-server-name")

    if TYPE_CHECKING:
        socket: Socket

        @property
        def dialer(self) -> _nng.nng_dialer: ...


class Listener(_base.Listener):
    """The Python version of `nng_listener
    <https://nanomsg.github.io/nng/man/tip/nng_listener.5>`_.  A
    :class:`Listener` is returned whenever :meth:`Socket.listen` is called.  A
    list of active listeners can be accessed via ``Socket.listeners``.

    A :class:`Listener` is associated with a single :class:`Socket`.  The
    associated socket can be accessed via the ``socket`` attribute.  There is
    no public constructor for creating a :class:`Listener`.

    """

    local_address = SockAddrOption("local-address")
    remote_address = SockAddrOption("remote-address")
    reconnect_time_min = MsOption("reconnect-time-min")
    reconnect_time_max = MsOption("reconnect-time-max")
    recv_max_size = SizeOption("recv-size-max")
    url = ReadOnlyStringOption("url")
    peer = ReadOnlyIntOption("peer")
    peer_name = ReadOnlyStringOption("peer-name")
    tcp_nodelay = BooleanOption("tcp-nodelay")
    tcp_keepalive = BooleanOption("tcp-keepalive")

    # v1-specific TLS options on the listener
    tls_config = PointerOption("tls-config")
    tls_ca_file = StringOption("tls-ca-file")
    tls_cert_key_file = StringOption("tls-cert-key-file")
    tls_auth_mode = IntOption("tls-authmode")
    tls_server_name = StringOption("tls-server-name")

    if TYPE_CHECKING:
        socket: Socket

        @property
        def listener(self) -> _nng.nng_listener: ...


class Context(_base.Context):
    """
    This is the Python version of `nng_context
    <https://nanomsg.github.io/nng/man/tip/nng_ctx.5.html>`_.  The way to
    create a :class:`Context` is by calling :meth:`Socket.new_context()`.
    Contexts are valid for :class:`Req0` and :class:`Rep0` sockets; other
    protocols do not support contexts.

    Once you have a context, you just call :meth:`~Context.send` and
    :meth:`~Context.recv` or the async equivalents as you would on a socket.

    A "context" keeps track of a protocol's state for stateful protocols (like
    REQ/REP).  A context allows the same :class:`Socket` to be used for
    multiple operations at the same time.  For an example of the problem that
    contexts are solving, see this snippet, **which does not use contexts**,
    and does terrible things:

    .. code-block:: python

        # start a socket to service requests.
        # HEY THIS IS EXAMPLE BAD CODE, SO DON'T TRY TO USE IT
        # in fact it's so bad it causes a panic in nng right now (2019/02/09):
        # see https://github.com/nanomsg/nng/issues/871
        import pynng
        import threading

        def service_reqs(s):
            while True:
                data = s.recv()
                s.send(b"I've got your response right here, pal!")


        threads = []
        with pynng.Rep0(listen='tcp://127.0.0.1:12345') as s:
            for _ in range(10):
                t = threading.Thread(target=service_reqs, args=[s], daemon=True)
                t.start()
                threads.append(t)

            for thread in threads:
                thread.join()

    Contexts allow multiplexing a socket in a way that is safe.  It removes one
    of the biggest use cases for needing to use raw sockets.

    Contexts cannot be instantiated directly; instead, create a
    :class:`Socket`, and call the :meth:`~Socket.new_context` method.

    """

    if TYPE_CHECKING:

        def recv_msg(self, block: bool = True) -> Message: ...

        def recv_msg_nowait(self) -> Message: ...

        async def arecv_msg(self) -> Message: ...


class Pipe(_base.Pipe):
    """
    A "pipe" is a single connection between two endpoints.  This is the Python
    version of `nng_pipe
    <https://nanomsg.github.io/nng/man/v1.1.0/nng_pipe.5>`_.

    There is no public constructor for a Pipe; they are automatically added to
    the underlying socket whenever the pipe is created.

    """

    local_address = SockAddrOption("local-address")
    remote_address = SockAddrOption("remote-address")
    url = ReadOnlyStringOption("url")
    protocol = ReadOnlyIntOption("protocol")
    protocol_name = ReadOnlyStringOption("protocol-name")
    peer = ReadOnlyIntOption("peer")
    peer_name = ReadOnlyStringOption("peer-name")

    if TYPE_CHECKING:
        socket: Socket

        @property
        def pipe(self) -> _nng.nng_pipe: ...

        @property
        def dialer(self) -> Dialer: ...

        @property
        def listener(self) -> Listener: ...


# Wire up the v1-specific subclasses so base class factory methods
# create v1 types (Context, Pipe, Dialer, Listener, Message) instead of _base types.
Socket._context_class = Context
Socket._pipe_class = Pipe
Socket._dialer_class = Dialer
Socket._listener_class = Listener


class Message(_base.Message):
    """
    Python interface for `nng_msg
    <https://nanomsg.github.io/nng/man/tip/nng_msg.5.html>`_.  Using the
    :class:`Message` interface gives more control over aspects of
    sending the message.  In particular, you can tell which
    :class:`Pipe` a message came from on receive, and you can direct
    which :class:`Pipe` a message will be sent from on send.

    In normal usage, you would not create a :class:`Message` directly.  Instead
    you would receive a message using :meth:`Socket.recv_msg`, and send a
    message (implicitly) by using :meth:`Pipe.send`.

    Since the main purpose of creating a :class:`Message` is to send it using a
    specific :class:`Pipe`, it is usually more convenient to just use the
    :meth:`Pipe.send` or :meth:`Pipe.asend` method directly.

    Messages in pynng are immutable; this is to prevent data corruption.

    Warning:

        Access to the message's underlying data buffer can be accessed with the
        ``_buffer`` attribute.  However, care must be taken not to send a message
        while a reference to the buffer is still alive; if the buffer is used after
        a message is sent, a segfault or data corruption may (read: will)
        result.

    """

    __slots__ = ()

    if TYPE_CHECKING:

        @property
        def pipe(self) -> Pipe | None: ...

        @pipe.setter
        def pipe(self, pipe: _base.Pipe) -> None: ...


Socket._message_class = Message

_F = TypeVar("_F", bound=Callable[..., object])


class _ExternDecorator(Protocol):
    def __call__(self, fn: _F, /) -> _F: ...


_def_extern: Callable[[], _ExternDecorator] = getattr(ffi, "def_extern")
_ffi_error: type[BaseException] = getattr(ffi, "error", RuntimeError)


@_def_extern()
def _nng_pipe_cb(lib_pipe: _nng.nng_pipe, event: int, arg: cffi.FFI.CData) -> None:
    logger.debug(f"Pipe callback event {event}")

    # Get the Socket from the handle passed through the callback arguments.
    # If the Socket has been GC'd and the handle is invalid, from_handle()
    # will crash. Guard against this by catching exceptions.
    try:
        sock: _base.Socket = ffi.from_handle(arg)
    except (RuntimeError, ValueError, _ffi_error):
        logger.info(
            "Pipe callback fired with invalid handle (socket likely GC'd); ignoring"
        )
        return

    _base._handle_pipe_event(sock, lib_pipe, event, lib)


def device(
    s1: _base.Socket | _nng.nng_socket | cffi.FFI.CData,
    s2: _base.Socket | _nng.nng_socket | cffi.FFI.CData | None = None,
) -> None:
    """Forward messages between socket s1 and socket s2 synchronously.

    If s2 is None, messages are forwarded in only one direction (from s1, which
    must be able to receive, to whatever destination). This function blocks
    until an error occurs or one of the sockets is closed.

    Args:
        s1: A :class:`Socket` instance.
        s2: A :class:`Socket` instance or None.

    Raises:
        Closed: When one of the sockets is closed.
        NNGException: If an NNG error occurs.
    """
    _device(s1, s2, lib, ffi)


def _device(
    s1: _base.Socket | _base._NngSocket | cffi.FFI.CData,
    s2: _base.Socket | _base._NngSocket | cffi.FFI.CData | None,
    default_lib: _base._NngLib,
    default_ffi: cffi.FFI,
) -> None:
    _base._check_fork()
    _base._mark_nng_initialized()
    _lib, _ffi, s1_raw, s2_raw = _base._device_sockets(s1, s2, default_lib, default_ffi)
    base_lib = cast(_base._BaseLibProtocol, _lib)
    owners = [s for s in (s1, s2) if isinstance(s, _base.Socket)]
    aio_p = _ffi.new("nng_aio **")
    check_err(base_lib.nng_aio_alloc(aio_p, _ffi.NULL, _ffi.NULL), lib=_lib, ffi=_ffi)
    aio: _base._NngAio = aio_p[0]
    try:
        _base._start_device(owners, _lib, aio, s1_raw, s2_raw)
        try:
            base_lib.nng_aio_wait(aio)
        finally:
            _base._stop_device(owners, aio)
        check_err(base_lib.nng_aio_result(aio), lib=_lib, ffi=_ffi)
    finally:
        base_lib.nng_aio_free(aio)


async def adevice(
    s1: _base.Socket | _nng.nng_socket | cffi.FFI.CData,
    s2: _base.Socket | _nng.nng_socket | cffi.FFI.CData | None = None,
    *,
    async_backend: str | None = None,
) -> None:
    """Forward messages between socket s1 and socket s2 asynchronously.

    Can be cancelled cleanly in asyncio and trio tasks.

    Args:
        s1: A :class:`Socket` instance.
        s2: A :class:`Socket` instance or None.
        async_backend: Async backend name ("asyncio" or "trio"), or None to auto-detect.

    Raises:
        Closed: When one of the sockets is closed.
        NNGException: If an NNG error occurs.
    """
    await _adevice(s1, s2, async_backend, lib, ffi)


async def _adevice(
    s1: _base.Socket | _base._NngSocket | cffi.FFI.CData,
    s2: _base.Socket | _base._NngSocket | cffi.FFI.CData | None,
    async_backend: str | None,
    default_lib: _base._NngLib,
    default_ffi: cffi.FFI,
) -> None:
    _base._check_fork()
    _base._mark_nng_initialized()
    with _aio.DeviceAIO(
        s1,
        s2,
        async_backend=async_backend,
        _default_lib=default_lib,
        _default_ffi=default_ffi,
    ) as dev:
        await dev.run()
