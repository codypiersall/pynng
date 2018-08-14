"""
Provides a Pythonic interface to cffi nng bindings
"""


from ._nng import ffi, lib as nng


__all__ = '''
ffi nng
Bus0
Pair0
Pair1
Pull0 Push0
Pub0 Sub0
Req0 Rep0
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
    def __init__(self, option_name):
        self.option = to_char(option_name)


class IntOption(_NNGOption):
    """Descriptor for getting/setting integers"""
    def __get__(self, instance, owner):
        return instance._getopt_int(self.option)

    def __set__(self, instance, value):
        instance._setopt_int(self.option, value)


class MsOption(_NNGOption):
    """Descriptor for getting/setting durations (in milliseconds)"""
    def __get__(self, instance, owner):
        return instance._getopt_ms(self.option)

    def __set__(self, instance, value):
        instance._setopt_ms(self.option, value)


class StringOption(_NNGOption):
    """Descriptor for getting/setting durations (in milliseconds)"""
    def __get__(self, instance, owner):
        return instance._getopt_string(self.option)

    def __set__(self, instance, value):
        instance._setopt_string(self.option, value)


def check_open(ret_val):
    if ret_val:
        raise Exception('TODO: Better exception')


class Socket:
    """The base socket.  It should not be instantiated directly."""

    def __init__(self, opener=None, *,
                 dial=None,
                 listen=None,
                 recv_timeout=None,
                 send_timeout=None
                 ):
        """Initialize socket.
        ``opener`` is the function in the ffi bindings used to initialize the
        specific socket.  For example, for a Pair1 socket, the function is
        ``ffi.nng_pair1_open``
        If ``dial`` is not None, attempt to dial the specified address.
        If ``listen`` is not None, attempt to listen at the specified address.
        If ``recv_timeout`` is not None, it is the receive timeout in ms.
        If ``send_timeout`` is not None, it is the receive timeout in ms.

        """
        self._socket_pointer = ffi.new('nng_socket[]', 1)
        if opener is not None:
            self.opener = opener
        if opener is None and not hasattr(self, 'opener'):
            raise TypeError('Cannot directly instantiate a Socket.  Try a subclass.')
        check_open(self.opener(self._socket_pointer))
        if dial is not None:
            self.dial(dial)
        if listen is not None:
            self.listen(listen)
        if recv_timeout is not None:
            self.recv_timeout = recv_timeout
        if send_timeout is not None:
            self.send_timeout = send_timeout

    def dial(self, address, dialer=ffi.NULL, flags=0):
        """Dial specified address; similar to nanomgs.connect().

        ``dialer`` and ``flags`` usually do not need to be given.
        """
        ret = nng.nng_dial(self.socket, to_char(address), dialer, flags)
        if ret:
            raise Exception('TODO: better exception')

    def listen(self, address, listener=ffi.NULL, flags=0):
        """Listen at specified address; similar to nanomsg.bind()

        ``listener`` and ``flags`` usually do not need to be given.
        """
        ret = nng.nng_listen(self.socket, to_char(address), listener, flags)
        if ret:
            raise Exception('TODO: better exception')

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
        if ret:
            raise Exception('TODO: better exception')
        recvd = ffi.unpack(data[0], size_t[0])
        nng.nng_free(data[0], size_t[0])
        return recvd

    def send(self, data):
        """Sends ``data`` on socket."""
        ret = nng.nng_send(self.socket, data, len(data), 0)
        if ret:
            raise Exception('TODO: better excecption')

    def _setopt_int(self, option, value):
        """Sets the specified option to the specified value"""
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        if not int(value) == value:
            raise Exception("TODO: better exception")
        value = int(value)
        nng.nng_setopt_int(self.socket, opt_as_char, value)

    def _getopt_int(self, option):
        """Gets the specified option"""
        i = ffi.new('int []', 1)
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        if nng.nng_getopt_int(self.socket, opt_as_char, i):
            raise Exception("TODO: better getopt exception")
        return i[0]

    def _setopt_ms(self, option, value):
        """Sets the specified option to the specified value"""
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        if not int(value) == value:
            raise Exception("TODO: better exception")
        value = int(value)
        nng.nng_setopt_ms(self.socket, opt_as_char, value)

    def _getopt_ms(self, option):
        """Gets the specified option"""
        ms = ffi.new('nng_duration []', 1)
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        if nng.nng_getopt_ms(self.socket, opt_as_char, ms):
            raise Exception("TODO: better getopt exception")
        return ms[0]

    def _setopt_string(self, option, value):
        """Sets the specified option to the specified value

        This is different than the library's nng_setopt_string, because it
        expects the string to be NULL terminated, and we don't.
        """
        opt_as_char = to_char(option)
        val_as_char = to_char(option)
        nng.nng_setopt(self.socket, opt_as_char, val_as_char, len(value))

    def _getopt_string(self, option):
        """Gets the specified option"""
        ms = ffi.new('nng_duration []', 1)
        opt_as_char = to_char(option)
        # attempt to accept floats that are exactly int
        if nng.nng_getopt_ms(self.socket, opt_as_char, ms):
            raise Exception("TODO: better getopt exception")
        return ms[0]

    def _setopt_bool(self, option, value):
        """Sets the specified option to the specified value"""
        opt_as_char = to_char(option)
        print(opt_as_char)
        # attempt to accept floats that are exactly int
        if nng.nng_setopt_int(self.socket, opt_as_char, value):
            raise Exception("TODO: Better setopt")

    recv_timeout = MsOption('recv-timeout')
    send_timeout = MsOption('send-timeout')


class Bus0(Socket):
    """A bus0 socket"""
    opener = nng.nng_bus0_open


class Pair0(Socket):
    """A pair0 socket."""
    opener = nng.nng_pair0_open


class Pair1(Socket):
    """A pair1 socket."""
    opener = nng.nng_pair1_open


class Pull0(Socket):
    """A pull0 socket."""
    opener = nng.nng_pull0_open


class Push0(Socket):
    """A push0 socket."""
    opener = nng.nng_push0_open


class Pub0(Socket):
    """A pub0 socket."""
    opener = nng.nng_pub0_open


class Sub0(Socket):
    """A Sub0 socket."""
    opener = nng.nng_sub0_open

    def subscribe(self, topic):
        """Subscribe to the specified topic."""
        self._setopt_string(b'sub:subscribe', topic)

    def unsubscribe(self, topic):
        """Unsubscribe to the specified topic."""
        self._setopt_string(b'sub:unsubscribe', topic)


class Req0(Socket):
    """A Req0 socket."""
    opener = nng.nng_req0_open


class Rep0(Socket):
    """A Rep0 socket."""
    opener = nng.nng_rep0_open


class Surveyor0(Socket):
    """A surveyor0 socket."""
    opener = nng.nng_surveyor0_open


class Respondent0(Socket):
    """A respondent0 socket."""
    opener = nng.nng_respondent0_open



