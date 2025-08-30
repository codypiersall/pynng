import socket
import struct

import pynng


class SockAddr:
    """
    Python wrapper for struct nng_sockaddr.

    """

    type_to_str = {
        pynng.lib.NNG_AF_UNSPEC: "Unspecified",
        pynng.lib.NNG_AF_INPROC: "inproc",
        pynng.lib.NNG_AF_IPC: "ipc",
        pynng.lib.NNG_AF_INET: "inet",
        pynng.lib.NNG_AF_INET6: "inetv6",
        pynng.lib.NNG_AF_ZT: "zerotier",
        pynng.lib.NNG_AF_ABSTRACT: "abstract",
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
        return "nng_sockaddr {{.family = {}}}".format(self.family)


class InprocAddr(SockAddr):
    def __init__(self, ffi_sock_addr):
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_inproc

    @property
    def name_bytes(self):
        name = pynng.ffi.string(self._mem.sa_name)
        return name

    @property
    def name(self):
        return self.name_bytes.decode()

    def __str__(self):
        return self.name


class IPCAddr(SockAddr):
    def __init__(self, ffi_sock_addr):
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_ipc

    @property
    def path_bytes(self):
        path = pynng.ffi.string(self._mem.sa_path)
        return path

    @property
    def path(self):
        return self.path_bytes.decode()

    def __str__(self):
        return self.path


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

    def __str__(self):
        as_bytes = struct.pack("I", self.addr)
        ip = socket.inet_ntop(socket.AF_INET, as_bytes)
        port = socket.ntohs(self.port)
        return "{}:{}".format(ip, port)


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

    def __str__(self):
        # TODO: not a good string repr at all
        ip = socket.inet_ntop(socket.AF_INET6, self.addr)
        port = socket.ntohs(self.port)
        return "[{}]:{}".format(ip, port)


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


class AbstractAddr(SockAddr):
    def __init__(self, ffi_sock_addr):
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_abstract

    @property
    def name_bytes(self):
        # Get the length of the name from sa_len
        name_len = self._mem.sa_len
        # Return the raw bytes of the name (up to name_len)
        return bytes(self._mem.sa_name[0:name_len])

    @property
    def name(self):
        # Decode the name bytes, handling any URI encoding
        import urllib.parse
        name_bytes = self.name_bytes
        try:
            # Try to decode as UTF-8 first
            name_str = name_bytes.decode('utf-8')
            # Unescape any URI-encoded characters
            return urllib.parse.unquote(name_str)
        except UnicodeDecodeError:
            # If UTF-8 decoding fails, return a representation of the bytes
            return repr(name_bytes)

    def __str__(self):
        # Return the abstract socket URI format
        import urllib.parse
        try:
            # Try to encode as UTF-8 and URI-encode
            name_str = self.name_bytes.decode('utf-8')
            encoded_name = urllib.parse.quote(name_str)
            return f"abstract://{encoded_name}"
        except UnicodeDecodeError:
            # If UTF-8 encoding fails, use a hex representation
            hex_name = self.name_bytes.hex()
            return f"abstract://{hex_name}"


def _nng_sockaddr(sa):
    # ensures the correct class gets instantiated based on s_family
    lookup = {
        pynng.lib.NNG_AF_INPROC: InprocAddr,
        pynng.lib.NNG_AF_IPC: IPCAddr,
        pynng.lib.NNG_AF_INET: InAddr,
        pynng.lib.NNG_AF_INET6: In6Addr,
        pynng.lib.NNG_AF_ZT: ZTAddr,
        pynng.lib.NNG_AF_ABSTRACT: AbstractAddr,
    }
    # fall through to SockAddr, e.g. if it's unspecified
    cls = lookup.get(sa[0].s_family, SockAddr)
    return cls(sa)
