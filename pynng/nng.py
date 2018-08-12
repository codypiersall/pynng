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
        lib.nng_dial(self.socket, convert_address(address), dialer, flags)

    def listen(self, address, listener=ffi.NULL, flags=0):
        """Listen at specified address; similar to nanomsg.bind()

        ``listener`` and ``flags`` usually do not need to be given.
        """
        lib.nng_listen(self.socket, convert_address(address), listener, flags)

    def close(self):
        lib.nng_close(self.socket)

    def __del__(self):
        self.close()

    @property
    def socket(self):
         return self._socket_pointer[0]

class Pair1Socket(Socket):
    """A Pair v1 socket."""
    def __init__(self):
        super().__init__()
        if lib.nng_pair1_open(self._socket_pointer):
            raise Exception('TODO: better exception')


PairSocket = Pair1Socket
