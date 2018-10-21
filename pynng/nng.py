"""
Provides a Pythonic interface to cffi nng bindings
"""

import logging

from ._nng import ffi, lib as nng
from .exceptions import check_err, ConnectionRefused


logger = logging.getLogger(__name__)


__all__ = '''
ffi nng
Bus0
Pair0
Pair1
Pull0 Push0
Pub0 Sub0
Req0 Rep0
Socket
Surveyor0 Respondent0
'''.split()


def _get_inst_and_func(wrapper_object, option_type, get_or_set):
    """
    Given the Python wrapper for one of nng's object types, return a tuple of
    (nng_object, nng_function).

    Args:
        wrapper_object Union(Socket, Dialer, Listener): the Python wrapper of
          the library type.
        option_type (str): The type of option.

    Returns:
        The tuple (nng_object, nng_func) for use in the module-level getopt*,
            setopt* functions

    """
    # map Python wrapper class to nng attribute
    nng_type_map = {
        Socket: 'socket',
        Dialer: 'dialer',
        Listener: 'listener'
    }

    option_to_func_map = {
        'int': 'nng_getopt_int',
        'size': 'nng_getopt_size',
        'ms': 'nng_getopt_ms',
        'string': 'nng_getopt_string',
        'bool': 'nng_getopt_bool',
        'sockaddr': 'nng_getopt_sockaddr',
    }

    t = type(wrapper_object)
    type_ok = True
    if issubclass(t, Socket):
        base_type = Socket
    elif issubclass(t, Dialer):
        base_type = Dialer
    elif issubclass(t, Listener):
        base_type = Listener
    option_ok = option_type in option_to_func_map
    get_ok = get_or_set in ('get', 'set')
    assert type_ok, 'The type {} is not supported'.format(t)
    assert option_ok, 'The option "{}" is not supported'.format(option_type)
    assert get_ok, 'get_or_set of "{}" is not supported'.format(get_or_set)

    obj = getattr(wrapper_object, nng_type_map[base_type])
    basic_funcname = option_to_func_map[option_type]
    if base_type is Socket:
        funcname = basic_funcname
    elif base_type is Dialer:
        funcname = basic_funcname.replace('nng_', 'nng_dialer_')
    elif base_type is Listener:
        funcname = basic_funcname.replace('nng_', 'nng_listener_')
    else:
        assert False

    if get_or_set == 'set':
        funcname = funcname.replace('getopt', 'setopt')
        # special-case for nng_setopt_string, which expects NULL-terminated
        # strings; we use the generic setopt in that case.
        if option_type == 'string':
            funcname = funcname.replace('_string', '')

    nng_func = getattr(nng, funcname)
    return obj, nng_func


def _getopt_int(obj, option):
    """Gets the specified option"""
    i = ffi.new('int []', 1)
    opt_as_char = to_char(option)
    obj, lib_func = _get_inst_and_func(obj, 'int', 'get')
    # attempt to accept floats that are exactly int
    ret = lib_func(obj, opt_as_char, i)
    check_err(ret)
    return i[0]


def _setopt_int(py_obj, option, value):
    """Sets the specified option to the specified value"""
    opt_as_char = to_char(option)
    # attempt to accept floats that are exactly int
    if not int(value) == value:
        msg = 'Invalid value {} of type {}.  Expected int.'
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    obj, lib_func = _get_inst_and_func(py_obj, 'int', 'set')
    value = int(value)
    err = lib_func(obj, opt_as_char, value)
    check_err(err)


def _getopt_size(py_obj, option):
    """Gets the specified size option"""
    i = ffi.new('size_t []', 1)
    opt_as_char = to_char(option)
    # attempt to accept floats that are exactly int
    obj, lib_func = _get_inst_and_func(py_obj, 'size', 'get')
    ret = lib_func(obj, opt_as_char, i)
    check_err(ret)
    return i[0]


def _setopt_size(py_obj, option, value):
    """Sets the specified size option to the specified value"""
    opt_as_char = to_char(option)
    # attempt to accept floats that are exactly int
    if not int(value) == value:
        msg = 'Invalid value {} of type {}.  Expected int.'
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    value = int(value)
    obj, lib_func = _get_inst_and_func(py_obj, 'size', 'set')
    lib_func(obj, opt_as_char, value)


def _getopt_ms(py_obj, option):
    """Gets the specified option"""
    ms = ffi.new('nng_duration []', 1)
    opt_as_char = to_char(option)
    obj, lib_func = _get_inst_and_func(py_obj, 'ms', 'get')
    ret = lib_func(obj, opt_as_char, ms)
    check_err(ret)
    return ms[0]


def _setopt_ms(py_obj, option, value):
    """Sets the specified option to the specified value"""
    opt_as_char = to_char(option)
    # attempt to accept floats that are exactly int (duration types are
    # just integers)
    if not int(value) == value:
        msg = 'Invalid value {} of type {}.  Expected int.'
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    value = int(value)
    obj, lib_func = _get_inst_and_func(py_obj, 'ms', 'set')
    lib_func(obj, opt_as_char, value)


def _getopt_string(py_obj, option):
    """Gets the specified string option"""
    opt = ffi.new('char *[]', 1)
    opt_as_char = to_char(option)
    obj, lib_func = _get_inst_and_func(py_obj, 'string', 'get')
    ret = lib_func(obj, opt_as_char, opt)
    check_err(ret)
    py_string = ffi.string(opt[0]).decode()
    nng.nng_strfree(opt[0])
    return py_string


def _setopt_string(py_obj, option, value):
    """Sets the specified option to the specified value

    This is different than the library's nng_setopt_string, because it
    expects the string to be NULL terminated, and we don't.
    """
    opt_as_char = to_char(option)
    val_as_char = to_char(value)
    obj, lib_func = _get_inst_and_func(py_obj, 'string', 'set')
    ret = lib_func(obj, opt_as_char, val_as_char, len(value))
    check_err(ret)


def _getopt_bool(py_obj, option):
    """Return the boolean value of the specified option"""
    opt_as_char = to_char(option)
    b = ffi.new('bool []', 1)
    obj, lib_func = _get_inst_and_func(py_obj, 'bool', 'get')
    ret = lib_func(obj, opt_as_char, b)
    check_err(ret)
    return b[0]


def _setopt_bool(py_obj, option, value):
    """Sets the specified option to the specified value."""
    opt_as_char = to_char(option)
    obj, lib_func = _get_inst_and_func(py_obj, 'bool', 'set')
    ret = lib_func(obj, opt_as_char, value)
    check_err(ret)


def _getopt_sockaddr(py_obj, option):
    opt_as_char = to_char(option)
    sock_addr = ffi.new('nng_sockaddr []', 1)
    obj, lib_func = _get_inst_and_func(py_obj, 'sockaddr', 'get')
    ret = lib_func(obj, opt_as_char, sock_addr)
    check_err(ret)
    return _nng_sockaddr(sock_addr)


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
    _getter = _getopt_int
    _setter = _setopt_int


class MsOption(_NNGOption):
    """Descriptor for getting/setting durations (in milliseconds)"""
    _getter = _getopt_ms
    _setter = _setopt_ms


class SockAddrOption(_NNGOption):
    """Descriptor for getting/setting durations (in milliseconds)"""
    _getter = _getopt_sockaddr


class SizeOption(_NNGOption):
    """Descriptor for getting/setting size_t options"""
    _getter = _getopt_size
    _setter = _setopt_size


class StringOption(_NNGOption):
    """Descriptor for getting/setting string options"""
    _getter = _getopt_string
    _setter = _setopt_string


class BooleanOption(_NNGOption):
    """Descriptor for getting/setting boolean values"""
    _getter = _getopt_bool
    _setter = _setopt_bool


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
    # TODO: does this belong here?
    ttl_max = IntOption('ttl-max')
    recv_max_size = SizeOption('recv-size-max')
    reconnect_time_min = MsOption('reconnect-time-min')
    reconnect_time_max = MsOption('reconnect-time-max')
    recv_fd = IntOption('recv-fd')
    send_fd = IntOption('send-fd')

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
                 block_on_dial=None
                 ):
        """Initialize socket.  It takes no positional arguments.
        Most socket options can be set through the initializer for convenience.
        the keyword function

        Note:
            The following arguments are all optional.

        Args:
            dial (str): The address to dial.  If not given, no address is
                dialed.  Note well: while the nng library
            listen (str): The address to listen at.  If not given, the socket
                does not listen at any address.
            recv_timeout: The receive timeout, in milliseconds.  If not given,
                there is no timeout.
            send_timeout: The send timeout, in milliseconds.  If not given,
                there is no timeout.
            recv_buffer_size: Set receive message buffer size.
            send_buffer_size: Sets send message buffer size.
            recv_max_size: Maximum size of message to receive.  Messages larger
                than this size are silently dropped.

        """
        # list of nng_dialers
        self._dialers = []
        self._listeners = []
        self._socket_pointer = ffi.new('nng_socket[]', 1)
        if opener is not None:
            self._opener = opener
        if opener is None and not hasattr(self, '_opener'):
            raise TypeError('Cannot directly instantiate a Socket.  Try a subclass.')
        check_err(self._opener(self._socket_pointer))
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
            self._dial(address, flags=nng.NNG_FLAG_NONBLOCK)

    def _dial(self, address, flags=0):
        """Dial specified address

        ``dialer`` and ``flags`` usually do not need to be given.
        """
        dialer = ffi.new('nng_dialer []', 1)
        ret = nng.nng_dial(self.socket, to_char(address), dialer, flags)
        check_err(ret)
        # we can only get here if check_err doesn't raise
        self._dialers.append(Dialer(dialer, self))

    def listen(self, address, flags=0):
        """Listen at specified address; similar to nanomsg.bind()

        ``listener`` and ``flags`` usually do not need to be given.
        """
        listener = ffi.new('nng_listener []', 1)
        ret = nng.nng_listen(self.socket, to_char(address), listener, flags)
        check_err(ret)
        # we can only get here if check_err doesn't raise
        self._listeners.append(Listener(listener, self))

    def close(self):
        """Close the socket, freeing all system resources."""
        nng.nng_close(self.socket)
        # cleanup the list of listeners/dialers.  A program would be likely to
        # segfault if a user accessed the listeners or dialers after this
        # point.
        self._listeners = []
        self._dialers = []

    def __del__(self):
        self.close()

    @property
    def socket(self):
        return self._socket_pointer[0]

    def recv(self):
        """recv() on the socket.  Allows the nanomsg library to allocate and
        manage the buffer, and calls nng_free afterward."""
        data = ffi.new('char *[]', 1)
        size_t = ffi.new('size_t []', 1)
        ret = nng.nng_recv(self.socket, data, size_t, nng.NNG_FLAG_ALLOC)
        check_err(ret)
        recvd = ffi.unpack(data[0], size_t[0])
        nng.nng_free(data[0], size_t[0])
        return recvd

    def send(self, data):
        """Sends ``data`` on socket."""
        err = nng.nng_send(self.socket, data, len(data), 0)
        check_err(err)

    def __enter__(self):
        return self

    def __exit__(self, *tb_info):
        self.close()

    @property
    def dialers(self):
        """A list of the active dialers"""
        # return a copy of the list, because we need to make sure we keep a
        # reference alive for cffi.  If someone else removes an item from the
        # list we return it doesn't matter.
        return self._dialers.copy()

    @property
    def listeners(self):
        """A list of the active listeners"""
        # return a copy of the list, because we need to make sure we keep a
        # reference alive for cffi.  If someone else removes an item from the
        # list we return it doesn't matter.
        return self._listeners.copy()


class Bus0(Socket):
    """A bus0 socket."""
    _opener = nng.nng_bus0_open


class Pair0(Socket):
    """A pair0 socket."""
    _opener = nng.nng_pair0_open


class Pair1(Socket):
    """A pair1 socket."""
    _opener = nng.nng_pair1_open


class Pull0(Socket):
    """A pull0 socket."""
    _opener = nng.nng_pull0_open


class Push0(Socket):
    """A push0 socket."""
    _opener = nng.nng_push0_open


class Pub0(Socket):
    """A pub0 socket."""
    _opener = nng.nng_pub0_open


class Sub0(Socket):
    """A sub0 socket."""
    _opener = nng.nng_sub0_open

    def subscribe(self, topic):
        """Subscribe to the specified topic."""
        _setopt_string(self, b'sub:subscribe', topic)

    def unsubscribe(self, topic):
        """Unsubscribe to the specified topic."""
        _setopt_string(self, b'sub:unsubscribe', topic)


class Req0(Socket):
    """A req0 socket."""
    _opener = nng.nng_req0_open


class Rep0(Socket):
    """A rep0 socket."""
    _opener = nng.nng_rep0_open


class Surveyor0(Socket):
    """A surveyor0 socket."""
    _opener = nng.nng_surveyor0_open


class Respondent0(Socket):
    """A respondent0 socket."""
    _opener = nng.nng_respondent0_open


class Dialer:
    """Wrapper class for the nng_dialer struct.

    You probably don't need to instantiate this directly.
    """
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

    local_address = SockAddrOption('local-address')
    remote_address = SockAddrOption('peer-address')
    reconnect_time_min = MsOption('reconnect-time-min')
    reconnect_time_max = MsOption('reconnect-time-max')
    recv_max_size = SizeOption('recv-size-max')
    url = StringOption('url')

    def close(self):
        """
        Close the dialer.
        """
        nng.nng_dialer_close(self.dialer)
        self.socket._dialers.remove(self)


class Listener:
    """Wrapper class for the nng_dialer struct."""
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
        nng.nng_listener_close(self.listener)
        self.socket._listeners.remove(self)

    local_address = SockAddrOption('local-address')
    remote_address = SockAddrOption('peer-address')
    recv_max_size = SizeOption('recv-size-max')
    url = StringOption('url')


class SockAddr:
    """
    Python wrapper for struct nng_sockaddr.

    """

    type_to_str = {
        nng.NNG_AF_UNSPEC: "Unspecified",
        nng.NNG_AF_INPROC: "inproc",
        nng.NNG_AF_IPC: "ipc",
        nng.NNG_AF_INET: "inet",
        nng.NNG_AF_INET6: "inetv6",
        nng.NNG_AF_ZT: "zerotier",
    }

    def __init__(self, ffi_sock_addr):
        self._sock_addr = ffi_sock_addr

    @property
    def sock_addr(self):
        return self._sock_addr[0]

    @property
    def family(self):
        """Return the integer representing the socket address family"""
        return self.sock_addr.s_family

    @property
    def family_as_str(self):
        """The string representation of the address family."""
        return self.type_to_str[self.family]

    def __repr__(self):
        return 'nng_sockaddr {{.family = {}}}'.format(self.family)


class InprocAddr(SockAddr):
    def __init__(self, ffi_sock_addr):
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_inproc

    @property
    def name_bytes(self):
        name = ffi.string(self._mem.sa_name)
        return name

    @property
    def name(self):
        return self.name_bytes.decode()


class IPCAddr(SockAddr):
    def __init__(self, ffi_sock_addr):
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_ipc

    @property
    def path_bytes(self):
        path = ffi.string(self._mem.sa_path)
        return path

    @property
    def path(self):
        return self.path_bytes.decode()


class InAddr(SockAddr):
    def __init__(self, ffi_sock_addr):
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_in

    @property
    def port(self):
        """Port, big-endian style"""
        return self._mem.sa_port

    @property
    def addr(self):
        """IP address as big-endian 32-bit number"""
        return self._mem.sa_addr


class In6Addr(SockAddr):
    def __init__(self, ffi_sock_addr):
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_in6

    @property
    def port(self):
        """Port, big-endian style"""
        return self._mem.sa_port

    @property
    def addr(self):
        """IP address as big-endian bytes"""
        return bytes(self._mem.sa_addr)


class ZTAddr(SockAddr):
    def __init__(self, ffi_sock_addr):
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_zt

    @property
    def nwid(self):
        return self._mem.as_nwid

    @property
    def nodeid(self):
        return self._mem.as_nodeid

    @property
    def port(self):
        return self._mem.as_port


def _nng_sockaddr(sa):
    # ensures the correct class gets instantiated based on s_family
    lookup = {
        nng.NNG_AF_INPROC: InprocAddr,
        nng.NNG_AF_IPC: IPCAddr,
        nng.NNG_AF_INET: InAddr,
        nng.NNG_AF_INET6: In6Addr,
        nng.NNG_AF_ZT: ZTAddr,
    }
    # fall through to SockAddr, e.g. if it's unspecified
    cls = lookup.get(sa[0].s_family, SockAddr)
    return cls(sa)
