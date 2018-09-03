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

    # subclasses set _getter and _setter to the names of the getter/setter
    # functions in the Socket class.
    _getter = None
    _setter = None

    def __init__(self, option_name):
        self.option = to_char(option_name)

    def __get__(self, instance, owner):
        getter = getattr(instance, self._getter)
        return getter(self.option)

    def __set__(self, instance, value):
        setter = getattr(instance, self._setter)
        setter(self.option, value)


class IntOption(_NNGOption):
    """Descriptor for getting/setting integer options"""
    _getter = '_getopt_int'
    _setter = '_setopt_int'


class MsOption(_NNGOption):
    """Descriptor for getting/setting durations (in milliseconds)"""
    _getter = '_getopt_ms'
    _setter = '_setopt_ms'


class SizeOption(_NNGOption):
    """Descriptor for getting/setting size_t options"""
    _getter = '_getopt_size'
    _setter = '_setopt_size'


class StringOption(_NNGOption):
    """Descriptor for getting/setting string options"""
    _getter = '_getopt_string'
    _setter = '_setopt_string'


class BooleanOption(_NNGOption):
    """Descriptor for getting/setting boolean values"""
    _getter = '_getopt_bool'
    _setter = '_setopt_bool'


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
            Corresponds to library option``NNG_OPT_RECVTIMEO`` *
        send_timeout (int): Send timeout, in ms.  If the message cannot be
            queued in the specified time, raises a pynng.exceptions.Timeout.
            Corresponds to library option ``NNG_OPT_SENDTIMEO``.
        local_address: Not implemented!!!  A read-only property representing
            the local address used for communication.  The Python wrapper for
            [nng_sockaddr](https://nanomsg.github.io/nng/man/v1.0.1/nng_sockaddr.5.html)
            needs to be completed first.  Corresponds to ``NNG_OPT_LOCADDR``.
        reconnect_time_min (int): The minimum time to wait before attempting
            reconnects, in ms.  Corresponds to ``NNG_OPT_RECONNMINT``.
        reconnect_time_max (int): The maximum time to wait before attempting
            reconnects, in ms.  Corresponds to ``NNG_OPT_RECONNMAXT``.  If this
            is non-zero, then the time between successive connection attempts
            will start at the value of reconnect_time_min, and grow
            exponentially, until it reaches this value.

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
    # TODO: local_address and rmeote_address are dialer/connected pipe options,
    # NOT socket options.
    local_address = NotImplementedOption(
        'local-address',
        'NNG_OPT_LOCADDR requires a Python wrapper for nng_sockaddr, which '
        'has not been done yet.'
    )
    remote_address = NotImplementedOption(
        'peer-address',
        'NNG_OPT_REMADDR requires a Python wrapper for nng_sockaddr, which '
        'has not been done yet.'
    )
    # TODO: url belongs on listner/dialers, not socket
    url = StringOption('url')
    # TODO: does this belong here?
    ttl_max = IntOption('ttl-max')
    recv_max_size = SizeOption('recv-size-max')
    reconnect_time_min = MsOption('reconnect-time-min')
    reconnect_time_max = MsOption('reconnect-time-max')

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
            recv_buffer_size: is not None, it sets receive message buffer size.

        """
        self._socket_pointer = ffi.new('nng_socket[]', 1)
        if opener is not None:
            self._opener = opener
        if opener is None and not hasattr(self, '_opener'):
            raise TypeError('Cannot directly instantiate a Socket.  Try a subclass.')
        check_err(self._opener(self._socket_pointer))
        if dial is not None:
            self.dial(dial, block=block_on_dial)
        if listen is not None:
            self.listen(listen)
        if recv_timeout is not None:
            self.recv_timeout = recv_timeout
        if send_timeout is not None:
            self.send_timeout = send_timeout

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

    def _dial(self, address, dialer=ffi.NULL, flags=0):
        """Dial specified address

        ``dialer`` and ``flags`` usually do not need to be given.
        """
        ret = nng.nng_dial(self.socket, to_char(address), dialer, flags)
        check_err(ret)

    def listen(self, address, listener=ffi.NULL, flags=0):
        """Listen at specified address; similar to nanomsg.bind()

        ``listener`` and ``flags`` usually do not need to be given.
        """
        ret = nng.nng_listen(self.socket, to_char(address), listener, flags)
        check_err(ret)

    def close(self):
        nng.nng_close(self.socket)

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

    def _getopt_int(self, option):
        """Gets the specified option"""
        i = ffi.new('int []', 1)
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        ret = nng.nng_getopt_int(self.socket, opt_as_char, i)
        check_err(ret)
        return i[0]

    def _setopt_int(self, option, value):
        """Sets the specified option to the specified value"""
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        if not int(value) == value:
            msg = 'Invalid value {} of type {}.  Expected int.'
            msg = msg.format(value, type(value))
            raise ValueError(msg)
        value = int(value)
        nng.nng_setopt_int(self.socket, opt_as_char, value)

    def _getopt_size(self, option):
        """Gets the specified size option"""
        i = ffi.new('size_t []', 1)
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        ret = nng.nng_getopt_size(self.socket, opt_as_char, i)
        check_err(ret)
        return i[0]

    def _setopt_size(self, option, value):
        """Sets the specified size option to the specified value"""
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        if not int(value) == value:
            msg = 'Invalid value {} of type {}.  Expected int.'
            msg = msg.format(value, type(value))
            raise ValueError(msg)
        value = int(value)
        nng.nng_setopt_size(self.socket, opt_as_char, value)

    def _getopt_ms(self, option):
        """Gets the specified option"""
        ms = ffi.new('nng_duration []', 1)
        opt_as_char = to_char(option)
        ret = nng.nng_getopt_ms(self.socket, opt_as_char, ms)
        check_err(ret)
        return ms[0]

    def _setopt_ms(self, option, value):
        """Sets the specified option to the specified value"""
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int (duration types are
        # just integers)
        if not int(value) == value:
            msg = 'Invalid value {} of type {}.  Expected int.'
            msg = msg.format(value, type(value))
            raise ValueError(msg)
        value = int(value)
        nng.nng_setopt_ms(self.socket, opt_as_char, value)

    def _getopt_string(self, option):
        """Gets the specified string option"""
        opt = ffi.new('char *[]', 1)
        opt_as_char = to_char(option)
        ret = nng.nng_getopt_string(self.socket, opt_as_char, opt)
        check_err(ret)
        py_obj = ffi.string(opt[0]).decode()
        nng.nng_strfree(opt[0])
        return py_obj

    def _setopt_string(self, option, value):
        """Sets the specified option to the specified value

        This is different than the library's nng_setopt_string, because it
        expects the string to be NULL terminated, and we don't.
        """
        opt_as_char = to_char(option)
        val_as_char = to_char(value)
        ret = nng.nng_setopt(self.socket, opt_as_char, val_as_char, len(value))
        check_err(ret)

    def _getopt_bool(self, option):
        """Return the boolean value of the specified option"""
        opt_as_char = to_char(option)
        b = ffi.new('bool []', 1)
        ret = nng.nng_getopt_bool(self.socket, opt_as_char, b)
        check_err(ret)
        return b[0]

    def _setopt_bool(self, option, value):
        """Sets the specified option to the specified value."""
        opt_as_char = to_char(option)
        ret = nng.nng_setopt_bool(self.socket, opt_as_char, value)
        check_err(ret)

    def __enter__(self):
        return self

    def __exit__(self, *tb_info):
        self.close()


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
    """A Sub0 socket."""
    _opener = nng.nng_sub0_open

    def subscribe(self, topic):
        """Subscribe to the specified topic."""
        self._setopt_string(b'sub:subscribe', topic)

    def unsubscribe(self, topic):
        """Unsubscribe to the specified topic."""
        self._setopt_string(b'sub:unsubscribe', topic)


class Req0(Socket):
    """A Req0 socket."""
    _opener = nng.nng_req0_open


class Rep0(Socket):
    """A Rep0 socket."""
    _opener = nng.nng_rep0_open


class Surveyor0(Socket):
    """A surveyor0 socket."""
    _opener = nng.nng_surveyor0_open


class Respondent0(Socket):
    """A respondent0 socket."""
    _opener = nng.nng_respondent0_open



