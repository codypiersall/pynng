"""
Provides a Pythonic interface to cffi nng bindings
"""


import logging
import weakref
import threading

from ._nng import ffi, lib
from .exceptions import check_err, ConnectionRefused
from . import options
from . import _aio


logger = logging.getLogger(__name__)

# a mapping of id(sock): sock for use in callbacks.  When a socket is
# initialized, it adds itself to this dict.  When a socket is closed, it
# removes itself from this dict.  In order to allow sockets to be garbage
# collected, a weak reference to the socket is stored here instead of the
# actual socket.

__all__ = '''
ffi
Bus0
Pair0
Pair1
Pull0 Push0
Pub0 Sub0
Req0 Rep0
Socket
Surveyor0 Respondent0
'''.split()

_live_sockets = weakref.WeakValueDictionary()


def to_char(charlike):
    """Convert str or bytes to char*."""
    # fast path for stuff that doesn't need to be changed.
    if isinstance(charlike, ffi.CData):
        return charlike
    if isinstance(charlike, str):
        charlike = charlike.encode()
    charlike = ffi.new('char[]', charlike)
    return charlike


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
            raise TypeError("{} cannot be set".format(self.__class__))
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


class NotImplementedOption(_NNGOption):
    """Represents a currently un-implemented option in Python."""
    def __init__(self, option_name, errmsg):
        super().__init__(option_name)
        self.errmsg = errmsg

    def __get__(self, instance, owner):
        raise NotImplementedError(self.errmsg)

    def __set__(self, instance, value):
        raise NotImplementedError(self.errmsg)


class Socket:
    """
    The base socket.  It should generally not be instantiated directly.
    See the documentation for __init__ for initialization options.

    Sockets have the following attributes:

    Attributes:
        name (str): The socket name.  Corresponds to ``NNG_OPT_SOCKNAME``.
            This is for debugging purposes.
        raw (bool): A boolean, indicating whether the socket is raw or cooked.
            Returns True if the socket is raw, else False.  This property is
            read-only.  Corresponds to library option ``NNG_OPT_RAW``.  For
            more information see
            https://nanomsg.github.io/nng/man/v1.0.1/nng.7.html#raw_mode.
        protocol (int): Read-only option which returns the 16-bit number of the
            socket's protocol.
        protocol_name (str): Read-only option which returns the name of the
            socket's protocol.
        peer (int): Returns the peer protocol id for the socket.
        recv_timeout (int): Receive timeout, in ms.  If a socket takes longer
            than the specified time, raises a pynng.exceptions.Timeout.
            Corresponds to library option``NNG_OPT_RECVTIMEO``
        send_timeout (int): Send timeout, in ms.  If the message cannot be
            queued in the specified time, raises a pynng.exceptions.Timeout.
            Corresponds to library option ``NNG_OPT_SENDTIMEO``.
        local_address: Not implemented!!!  A read-only property representing
            the local address used for communication.  The Python wrapper for
            [nng_sockaddr](https://nanomsg.github.io/nng/man/v1.0.1/nng_sockaddr.5.html)
            needs to be completed first.  Corresponds to ``NNG_OPT_LOCADDR``.
        reconnect_time_min (int): The minimum time to wait before attempting
            reconnects, in ms.  Corresponds to ``NNG_OPT_RECONNMINT``.  This
            can also be overridden on the dialers.
        reconnect_time_max (int): The maximum time to wait before attempting
            reconnects, in ms.  Corresponds to ``NNG_OPT_RECONNMAXT``.  If this
            is non-zero, then the time between successive connection attempts
            will start at the value of reconnect_time_min, and grow
            exponentially, until it reaches this value.  This option can be set
            on the socket, or on the dialers associated with the socket.
        recv_fd (int): The receive file descriptor associated with the socket.
            This is suitable to be passed into poll functions like poll(),
            or select().
        send_fd (int): The sending file descriptor associated with the socket.
            This is suitable to be passed into poll functions like poll(),
            or select().
        recv_max_size (int): The largest size of a message to receive.
            Messages larger than this size will be silently dropped.  A size of
            -1 indicates unlimited size.

    See also the nng man pages document for options:

    https://nanomsg.github.io/nng/man/v1.0.1/nng_options.5.html
    """

    # the following options correspond to nng options documented at
    # https://nanomsg.github.io/nng/man/v1.0.1/nng_options.5.html
    name = StringOption('socket-name')
    raw = BooleanOption('raw')
    protocol = IntOption('protocol')
    protocol_name = StringOption('protocol-name')
    peer = IntOption('peer')
    peer_name = StringOption('peer-name')
    recv_buffer_size = IntOption('recv-buffer')
    send_buffer_size = IntOption('send-buffer')
    recv_timeout = MsOption('recv-timeout')
    send_timeout = MsOption('send-timeout')
    ttl_max = IntOption('ttl-max')
    recv_max_size = SizeOption('recv-size-max')
    reconnect_time_min = MsOption('reconnect-time-min')
    reconnect_time_max = MsOption('reconnect-time-max')
    recv_fd = IntOption('recv-fd')
    send_fd = IntOption('send-fd')
    tcp_nodelay = BooleanOption('tcp-nodelay')
    tcp_keepalive = BooleanOption('tcp-keepalive')

    def __init__(self, *,
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
                 block_on_dial=None,
                 name=None,
                 async_backend=None
                 ):
        """Initialize socket.  It takes no positional arguments.
        Most socket options can be set through the initializer for convenience.

        Note:
            The following arguments are all optional.

        Args:
            dial: The address to dial.  If not given, no address is dialed.
            listen: The address to listen at.  If not given, the socket does
                not listen at any address.
            recv_timeout: The receive timeout, in milliseconds.  If not given,
                there is no timeout.
            send_timeout: The send timeout, in milliseconds.  If not given,
                there is no timeout.
            recv_buffer_size: Set receive message buffer size.
            send_buffer_size: Sets send message buffer size.
            recv_max_size: Maximum size of message to receive.  Messages larger
                than this size are silently dropped.
            async_backend: The event loop backend for asyncronous socket
                operations.  the currently supported backends are "asyncio" and
                "trio".  If ``async_backend`` is not provided, pynng will use
                sniffio to attempt to find the currently running event loop.

        """
        # mapping of id: Python objects
        self._dialers = {}
        self._listeners = {}
        self._pipes = {}
        self._on_pre_pipe_add = []
        self._on_post_pipe_add = []
        self._on_post_pipe_remove = []
        self._pipe_notify_lock = threading.Lock()
        self._async_backend = async_backend
        self._socket = ffi.new('nng_socket *',)
        if opener is not None:
            self._opener = opener
        if opener is None and not hasattr(self, '_opener'):
            raise TypeError('Cannot directly instantiate a Socket.  Try a subclass.')
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
        if listen is not None:
            self.listen(listen)
        if dial is not None:
            self.dial(dial, block=block_on_dial)

        _live_sockets[id(self)] = self
        as_void = ffi.cast('void *', id(self))
        # set up pipe callbacks
        check_err(lib.nng_pipe_notify(self.socket, lib.NNG_PIPE_EV_ADD_PRE,
                                      lib._nng_pipe_cb, as_void))
        check_err(lib.nng_pipe_notify(self.socket, lib.NNG_PIPE_EV_ADD_POST,
                                      lib._nng_pipe_cb, as_void))
        check_err(lib.nng_pipe_notify(self.socket, lib.NNG_PIPE_EV_REM_POST,
                                      lib._nng_pipe_cb, as_void))

    def dial(self, address, *, block=None):
        """Dial the specified address.

        Args:
            addres:  The address to dial.
            block:  Whether to block or not.  There are three possible values
                this can take:

                1. If truthy, a blocking dial is attempted.  If it fails for
                   any reason, an exception is raised.
                2. If Falsy, a non-blocking dial is started.  The dial is
                   retried periodically in the background until it is
                   successful.
                3. (**Default behavior**): If ``None``, which a blocking dial
                   is first attempted. If it fails an exception is logged
                   (using the Python logging module), then a non-blocking dial
                   is done.

        """
        if block:
            self._dial(address, flags=0)
        elif block is None:
            try:
                self.dial(address, block=False)
            except ConnectionRefused:
                msg = 'Synchronous dial failed; attempting asynchronous now'
                logger.exception(msg)
                self.dial(address, block=False)
        else:
            self._dial(address, flags=lib.NNG_FLAG_NONBLOCK)

    def _dial(self, address, flags=0):
        """Dial specified address

        ``dialer`` and ``flags`` usually do not need to be given.
        """
        dialer = ffi.new('nng_dialer *')
        ret = lib.nng_dial(self.socket, to_char(address), dialer, flags)
        check_err(ret)
        # we can only get here if check_err doesn't raise
        d_id = lib.nng_dialer_id(dialer[0])
        self._dialers[d_id] = Dialer(dialer, self)

    def listen(self, address, flags=0):
        """Listen at specified address; similar to nanomsg.bind()

        ``listener`` and ``flags`` usually do not need to be given.
        """
        listener = ffi.new('nng_listener *')
        ret = lib.nng_listen(self.socket, to_char(address), listener, flags)
        check_err(ret)
        # we can only get here if check_err doesn't raise
        l_id = lib.nng_listener_id(listener[0])
        self._listeners[l_id] = Listener(listener, self)

    def close(self):
        """Close the socket, freeing all system resources."""
        # if a TypeError occurs (e.g. a bad keyword to __init__) we don't have
        # the attribute _socket yet.  This prevents spewing extra exceptions
        if hasattr(self, '_socket'):
            lib.nng_close(self.socket)
            # cleanup the list of listeners/dialers.  A program would be likely to
            # segfault if a user accessed the listeners or dialers after this
            # point.
            self._listeners = {}
            self._dialers = {}

    def __del__(self):
        self.close()

    @property
    def socket(self):
        return self._socket[0]

    def recv(self, block=True):
        """Receive data on the socket.

        Args:

          block: If block is True (the default), the function will not return
            until the operation is completed or times out.  If block is False,
            the function will return data immediately.  If no data is ready on
            the socket, the function will raise ``pynng.TryAgain``.

        """
        # TODO: someday we should support some kind of recv_into() operation
        # where the user provides the data buffer.
        flags = lib.NNG_FLAG_ALLOC
        if not block:
            flags |= lib.NNG_FLAG_NONBLOCK
        data = ffi.new('char **')
        size_t = ffi.new('size_t *')
        ret = lib.nng_recv(self.socket, data, size_t, flags)
        check_err(ret)
        recvd = ffi.unpack(data[0], size_t[0])
        lib.nng_free(data[0], size_t[0])
        return recvd

    def send(self, data):
        """Sends ``data`` on socket."""
        err = lib.nng_send(self.socket, data, len(data), 0)
        check_err(err)

    async def arecv(self):
        """Asynchronously receive a message."""
        with _aio.AIOHelper(self, self._async_backend) as aio:
            return await aio.arecv()

    async def asend(self, data):
        """Asynchronously send a message."""
        with _aio.AIOHelper(self, self._async_backend) as aio:
            return await aio.asend(data)

    def __enter__(self):
        return self

    def __exit__(self, *tb_info):
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
        return tuple(self._pipes.values())

    def _add_pipe(self, lib_pipe):
        # this is only called inside the pipe callback.
        pipe_id = lib.nng_pipe_id(lib_pipe)
        pipe = Pipe(lib_pipe, self)
        self._pipes[pipe_id] = pipe
        return pipe

    def _remove_pipe(self, lib_pipe):
        pipe_id = lib.nng_pipe_id(lib_pipe)
        del self._pipes[pipe_id]

    def new_context(self):
        """
        Return a new Context for this socket.
        """
        return Context(self)

    def new_contexts(self, n):
        """
        Return ``n`` new contexts for this socket
        """
        return [self.new_context() for _ in range(n)]

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
        self._on_pre_pipe_add.append(callback)

    def add_post_pipe_connect_cb(self, callback):
        """
        Add a callback which will be called after a Pipe is connected to a
        Socket.  You can add as many callbacks as you want, and they will be
        called in the order they were added.

        The callback provided must accept a single argument: a Pipe.

        """
        self._on_post_pipe_add.append(callback)

    def add_post_pipe_remove_cb(self, callback):
        """
        Add a callback which will be called after a Pipe is removed from a
        Socket.  You can add as many callbacks as you want, and they will be
        called in the order they were added.

        The callback provided must accept a single argument: a Pipe.

        """
        self._on_post_pipe_remove.append(callback)

    def remove_pre_pipe_connect_cb(self, callback):
        """
        Remove ``callback`` from the list of callbacks for pre pipe connect
        events
        """
        self._on_pre_pipe_add.remove(callback)

    def remove_post_pipe_connect_cb(self, callback):
        """
        Remove ``callback`` from the list of callbacks for post pipe connect
        events
        """
        self._on_post_pipe_add.remove(callback)

    def remove_post_pipe_remove_cb(self, callback):
        """
        Remove ``callback`` from the list of callbacks for post pipe remove
        events
        """
        self._on_post_pipe_remove.remove(callback)


class Bus0(Socket):
    """A bus0 socket."""
    _opener = lib.nng_bus0_open


class Pair0(Socket):
    """A pair0 socket."""
    _opener = lib.nng_pair0_open


class Pair1(Socket):
    """A pair1 socket."""
    _opener = lib.nng_pair1_open


class Pull0(Socket):
    """A pull0 socket."""
    _opener = lib.nng_pull0_open


class Push0(Socket):
    """A push0 socket."""
    _opener = lib.nng_push0_open


class Pub0(Socket):
    """A pub0 socket."""
    _opener = lib.nng_pub0_open


class Sub0(Socket):
    """A sub0 socket."""
    _opener = lib.nng_sub0_open

    def subscribe(self, topic):
        """Subscribe to the specified topic."""
        options._setopt_string(self, b'sub:subscribe', topic)

    def unsubscribe(self, topic):
        """Unsubscribe to the specified topic."""
        options._setopt_string(self, b'sub:unsubscribe', topic)


class Req0(Socket):
    """A req0 socket."""
    _opener = lib.nng_req0_open


class Rep0(Socket):
    """A rep0 socket."""
    _opener = lib.nng_rep0_open


class Surveyor0(Socket):
    """A surveyor0 socket."""
    _opener = lib.nng_surveyor0_open


class Respondent0(Socket):
    """A respondent0 socket."""
    _opener = lib.nng_respondent0_open


class Dialer:
    """Wrapper class for the nng_dialer struct.

    You probably don't need to instantiate this directly.
    """

    local_address = SockAddrOption('local-address')
    remote_address = SockAddrOption('remote-address')
    reconnect_time_min = MsOption('reconnect-time-min')
    reconnect_time_max = MsOption('reconnect-time-max')
    recv_max_size = SizeOption('recv-size-max')
    url = StringOption('url')
    peer = IntOption('peer')
    peer_name = StringOption('peer-name')
    tcp_nodelay = BooleanOption('tcp-nodelay')
    tcp_keepalive = BooleanOption('tcp-keepalive')

    def __init__(self, dialer, socket):
        """
        Args:
            dialer: the initialized `lib.nng_dialer`.
            socket: The Socket associated with the dialer

        """
        # I can't think of a reason you would need to directly instantiate this
        # class
        self._dialer = dialer
        self.socket = socket

    @property
    def dialer(self):
        return self._dialer[0]

    def close(self):
        """
        Close the dialer.
        """
        lib.nng_dialer_close(self.dialer)
        del self.socket._dialers[self.id]

    @property
    def id(self):
        return lib.nng_dialer_id(self.dialer)


class Listener:
    """Wrapper class for the nng_dialer struct."""

    local_address = SockAddrOption('local-address')
    remote_address = SockAddrOption('remote-address')
    reconnect_time_min = MsOption('reconnect-time-min')
    reconnect_time_max = MsOption('reconnect-time-max')
    recv_max_size = SizeOption('recv-size-max')
    url = StringOption('url')
    peer = IntOption('peer')
    peer_name = StringOption('peer-name')
    tcp_nodelay = BooleanOption('tcp-nodelay')
    tcp_keepalive = BooleanOption('tcp-keepalive')

    def __init__(self, listener, socket):
        """
        Args:
            listener: the initialized `lib.nng_dialer`.
            socket: The Socket associated with the dialer

        """
        # I can't think of a reason you would need to directly instantiate this
        # class
        self._listener = listener
        self.socket = socket

    @property
    def listener(self):
        return self._listener[0]

    def close(self):
        """
        Close the dialer.
        """
        lib.nng_listener_close(self.listener)
        del self.socket._listeners[self.id]

    @property
    def id(self):
        return lib.nng_listener_id(self.listener)


class Context:
    """
    A "context" keeps track of a protocol's state for stateful protocols (like
    REQ/REP).  A context allows the same socket to be used for multiple
    operations at the same time.  For example, the following code, **which does
    not use contexts**, does terrible things:

    .. code-block:: python

        # start a socket to service requests.
        # HEY THIS IS EXAMPLE BAD CODE, SO DON'T TRY TO USE IT
        import pynng
        import threading

        def service_reqs(s):
            while True:
                data = s.recv()
                # do something with data, e.g.
                s.send(b"here's your answer, pal!")


        threads = []
        with pynng.Rep0(listen='tcp:127.0.0.1:12345') as s:
            for _ in range(10):
                t = threading.Thread(target=service_reqs, args=[s], daemon=True)
                t.start()
                threads.append(t)

            for thread in threads:
                thread.join()

    Contexts allow multiplexing a socket in a way that is safe.  It removes one
    of the biggest use cases for needing to use raw sockets.

    Contexts should not be instantiated directly; instead, create a socket, and
    call the new_context() method.
    """

    def __init__(self, socket):
        # need to set attributes first, so that if anything goes wrong,
        # __del__() doesn't throw an AttributeError
        self._context = None
        assert isinstance(socket, Socket)
        self._socket = socket
        self._context = ffi.new('nng_ctx *')
        check_err(lib.nng_ctx_open(self._context, socket.socket))

        assert lib.nng_ctx_id(self.context) != -1

    async def arecv(self):
        """
        Asynchronously receive data using this context.
        """
        with _aio.AIOHelper(self, self._socket._async_backend) as aio:
            return await aio.arecv()

    async def asend(self, data):
        """
        Asynchronously send data using this context.
        """
        with _aio.AIOHelper(self, self._socket._async_backend) as aio:
            return await aio.asend(data)

    def recv(self):
        """
        Synchronously receive data on this context.
        """
        aio_p = ffi.new('nng_aio **')
        check_err(lib.nng_aio_alloc(aio_p, ffi.NULL, ffi.NULL))
        aio = aio_p[0]
        try:
            check_err(lib.nng_ctx_recv(self.context, aio))
            check_err(lib.nng_aio_wait(aio))
            check_err(lib.nng_aio_result(aio))
            msg = lib.nng_aio_get_msg(aio)
            try:
                size = lib.nng_msg_len(msg)
                data = ffi.cast('char *', lib.nng_msg_body(msg))
                py_obj = bytes(ffi.buffer(data[0:size]))
            finally:
                lib.nng_msg_free(msg)
        finally:
            lib.nng_aio_free(aio)
        return py_obj

    def send(self, data):
        """
        Synchronously send data on the socket.
        """
        aio_p = ffi.new('nng_aio **')
        check_err(lib.nng_aio_alloc(aio_p, ffi.NULL, ffi.NULL))
        aio = aio_p[0]
        try:
            msg_p = ffi.new('nng_msg **')
            check_err(lib.nng_msg_alloc(msg_p, 0))
            msg = msg_p[0]
            lib.nng_msg_append(msg, data, len(data))
            check_err(lib.nng_aio_set_msg(aio, msg))
            check_err(lib.nng_ctx_send(self.context, aio))
            check_err(lib.nng_aio_wait(aio))
            check_err(lib.nng_aio_result(aio))
        finally:
            lib.nng_aio_free(aio)

    def _free(self):
        ctx_err = 0
        if self._context is not None:
            if lib.nng_ctx_id(self.context) != -1:
                ctx_err = lib.nng_ctx_close(self.context)
                self._context = None
                check_err(ctx_err)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._free()

    @property
    def context(self):
        """Return the underlying nng object."""
        return self._context[0]

    def __del__(self):
        self._free()


@ffi.def_extern()
def _nng_pipe_cb(lib_pipe, event, arg):
    sock_id = int(ffi.cast('size_t', arg))
    sock = _live_sockets[sock_id]
    # exceptions don't propagate out of this function, so if any exception is
    # raised in any of the callbacks, we just log it (using logger.exception).
    with sock._pipe_notify_lock:
        pipe_id = lib.nng_pipe_id(lib_pipe)
        if event == lib.NNG_PIPE_EV_ADD_PRE:
            # time to do our bookkeeping; actually create the pipe and attach it to
            # the socket
            pipe = sock._add_pipe(lib_pipe)
            for cb in sock._on_pre_pipe_add:
                try:
                    cb(pipe)
                except:
                    msg = 'Exception raised in pre pipe connect callback'
                    logger.exception(msg)
            if pipe.closed:
                # NB: we need to remove the pipe from socket now, before a remote
                # tries connecting again and the same pipe ID may be reused.  This
                # will result in a KeyError below.
                sock._remove_pipe(lib_pipe)
        elif event == lib.NNG_PIPE_EV_ADD_POST:
            pipe = sock._pipes[pipe_id]
            for cb in sock._on_post_pipe_add:
                try:
                    cb(pipe)
                except:
                    msg = 'Exception raised in post pipe connect callback'
                    logger.exception(msg)
        elif event == lib.NNG_PIPE_EV_REM_POST:
            try:
                pipe = sock._pipes[pipe_id]
            except KeyError:
                # we get here if the pipe was closed in pre_connect earlier. This
                # is not a big deal.
                logger.debug('Could not find pipe for socket')
                return
            try:
                for cb in sock._on_post_pipe_remove:
                    try:
                        cb(pipe)
                    except:
                        msg = 'Exception raised in post pipe remove callback'
                        logger.exception(msg)
            finally:
                sock._remove_pipe(lib_pipe)


class Pipe:
    """
    A "pipe" is a single connection between two endpoints.
    https://nanomsg.github.io/nng/man/v1.1.0/nng_pipe.5.

    There is no public constructor for a Pipe; they are automatically added to
    the underlying socket whenever the pipe is created.

    """

    local_address = SockAddrOption('local-address')
    remote_address = SockAddrOption('remote-address')
    url = StringOption('url')
    protocol = IntOption('protocol')
    protocol_name = StringOption('protocol-name')
    peer = IntOption('peer')
    peer_name = StringOption('peer-name')
    tcp_nodelay = BooleanOption('tcp-nodelay')
    tcp_keepalive = BooleanOption('tcp-keepalive')

    def __init__(self, lib_pipe, socket):
        # Ohhhhkay
        # so
        # this is weird, I know
        # okay
        # so
        # For some reason, I'm not sure why, if we keep a reference to lib_pipe
        # directly, we end up with memory corruption issues.  Maybe it's a
        # weird interaction between getting called in a callback and refcount
        # or something, I dunno.  Anyway, we need to make a copy of the
        # lib_pipe object.
        self._pipe = ffi.new('nng_pipe *')
        self._pipe[0] = lib_pipe
        self.pipe = self._pipe[0]
        self.socket = socket
        self._closed = False

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
        return lib.nng_pipe_id(self.pipe)

    @property
    def dialer(self):
        """
        Return the dialer this pipe is associated with.  If the pipe is not
        associated with a dialer, raise an exception

        """
        dialer = lib.nng_pipe_dialer(self.pipe)
        d_id = lib.nng_dialer_id(dialer)
        if d_id < 0:
            # TODO: Different exception?
            raise TypeError('This pipe has no associated dialers.')
        return self.socket._dialers[d_id]

    @property
    def listener(self):
        """
        Return the listener this pipe is associated with.  If the pipe is not
        associated with a listener, raise an exception

        """
        listener = lib.nng_pipe_listener(self.pipe)
        l_id = lib.nng_listener_id(listener)
        if l_id < 0:
            # TODO: Different exception?
            raise TypeError('This pipe has no associated listeners.')
        return self.socket._listeners[l_id]

    def close(self):
        """
        Close the pipe.

        """
        check_err(lib.nng_pipe_close(self.pipe))
        self._closed = True

