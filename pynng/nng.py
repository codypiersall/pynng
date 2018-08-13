"""
Provides a Pythonic interface to cffi nng bindings
"""


from ._nng import ffi, lib


def convert_address(addr):
    """Convert str or bytes to char*."""
    if isinstance(addr, str):
        addr = addr.encode()
    if not isinstance(addr, ffi.CData):
        addr = ffi.new('char[]', addr)
    return addr


class Socket:
    """The base socket.  It should not be instantiated directly."""
    def __init__(self):
        self._socket_pointer = ffi.new('nng_socket[]', 1)

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
        the_data = ffi.unpack(data[0], size_t[0])
        lib.nng_free(data[0], len(data))
        return the_data

    def send(self, data):
        """

        Sends ``data`` on socket.

        """
        lib.nng_send(self.socket, data, len(data), 0)


class Pair1Socket(Socket):
    """A Pair v1 socket."""
    def __init__(self):
        super().__init__()
        if lib.nng_pair1_open(self._socket_pointer):
            raise Exception('TODO: better exception')


PairSocket = Pair1Socket
