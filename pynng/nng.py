"""
Provides a Pythonic interface to cffi nng bindings
"""


from ._nng import ffi, lib


__all__ = '''
ffi lib
Bus0
Pair0
Pair1
Pull0 Push0
Pub0 Sub0
Req0 Rep0
Surveyor0 Respondent0
'''.split()


def convert_address(addr):
    """Convert str or bytes to char*."""
    if isinstance(addr, str):
        addr = addr.encode()
    if not isinstance(addr, ffi.CData):
        addr = ffi.new('char[]', addr)
    return addr


def check_open(ret_val):
    if ret_val:
        raise Exception('TODO: Better exception')


class Socket:
    """The base socket.  It should not be instantiated directly."""

    def __init__(self, opener=None, dial=None, listen=None):
        """Initialize socket.
        ``opener`` is the function in the ffi bindings used to initialize the
        specific socket.  For example, for a Pair1 socket, the function is
        ``ffi.nng_pair1_open``
        If ``dial`` is not None, attempt to dial the specified address.
        If ``listen`` is not None, attempt to listen at the specified address.

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

    def dial(self, address, dialer=ffi.NULL, flags=0):
        """Dial specified address; similar to nanomgs.connect().

        ``dialer`` and ``flags`` usually do not need to be given.
        """
        ret = lib.nng_dial(self.socket, convert_address(address), dialer, flags)
        if ret:
            raise Exception('TODO: better exception')

    def listen(self, address, listener=ffi.NULL, flags=0):
        """Listen at specified address; similar to nanomsg.bind()

        ``listener`` and ``flags`` usually do not need to be given.
        """
        ret = lib.nng_listen(self.socket, convert_address(address), listener, flags)
        if ret:
            raise Exception('TODO: better exception')

    def close(self):
        lib.nng_close(self.socket)

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
        ret = lib.nng_recv(self.socket, data, size_t, lib.NNG_FLAG_ALLOC)
        if ret:
            raise Exception('TODO: better exception')
        recvd = ffi.unpack(data[0], size_t[0])
        lib.nng_free(data[0], size_t[0])
        return recvd

    def send(self, data):
        """

        Sends ``data`` on socket.

        """

        lib.nng_send(self.socket, data, len(data), 0)


class Bus0(Socket):
    """A bus0 socket"""
    opener = lib.nng_bus0_open


class Pair0(Socket):
    """A pair0 socket."""
    opener = lib.nng_pair0_open


class Pair1(Socket):
    """A pair1 socket."""
    opener = lib.nng_pair1_open


class Pull0(Socket):
    """A pull0 socket."""
    opener = lib.nng_pull0_open


class Push0(Socket):
    """A push0 socket."""
    opener = lib.nng_push0_open


class Pub0(Socket):
    """A pub0 socket."""
    opener = lib.nng_pub0_open


class Sub0(Socket):
    """A Sub0 socket."""
    opener = lib.nng_sub0_open


class Req0(Socket):
    """A Req0 socket."""
    opener = lib.nng_req0_open


class Rep0(Socket):
    """A Rep0 socket."""
    opener = lib.nng_rep0_open


class Surveyor0(Socket):
    """A surveyor0 socket."""
    opener = lib.nng_surveyor0_open


class Respondent0(Socket):
    """A respondent0 socket."""
    opener = lib.nng_respondent0_open



