from __future__ import annotations

import socket
import struct
from typing import TYPE_CHECKING, cast
import urllib.parse

import pynng

if TYPE_CHECKING:
    import cffi

    from . import _nng, _nng_v2


class SockAddr:
    """
    Python wrapper for struct nng_sockaddr.

    """

    __slots__ = ("_sock_addr",)

    type_to_str: dict[int, str] = {
        pynng.lib.NNG_AF_UNSPEC: "Unspecified",
        pynng.lib.NNG_AF_INPROC: "inproc",
        pynng.lib.NNG_AF_IPC: "ipc",
        pynng.lib.NNG_AF_INET: "inet",
        pynng.lib.NNG_AF_INET6: "inetv6",
        pynng.lib.NNG_AF_ZT: "zerotier",
        pynng.lib.NNG_AF_ABSTRACT: "abstract",
    }

    def __init__(self, ffi_sock_addr: cffi.FFI.CData) -> None:
        self._sock_addr = ffi_sock_addr

    @property
    def sock_addr(self) -> _nng.nng_sockaddr | _nng_v2.nng_sockaddr:
        return cast("_nng.nng_sockaddr | _nng_v2.nng_sockaddr", self._sock_addr[0])

    @property
    def family(self) -> int:
        """Return the integer representing the socket address family"""
        return int(self.sock_addr.s_family)

    @property
    def family_as_str(self) -> str:
        """The string representation of the address family."""
        return self.type_to_str[self.family]

    def __repr__(self) -> str:
        return f"nng_sockaddr {{.family = {self.family}}}"


class InprocAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(self, ffi_sock_addr: cffi.FFI.CData) -> None:
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_inproc

    @property
    def name_bytes(self) -> bytes:
        name = pynng.ffi.string(cast("cffi.FFI.CData", self._mem.sa_name))
        return name if isinstance(name, bytes) else name.encode()

    @property
    def name(self) -> str:
        return self.name_bytes.decode()

    def __str__(self) -> str:
        return self.name


class IPCAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(self, ffi_sock_addr: cffi.FFI.CData) -> None:
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_ipc

    @property
    def path_bytes(self) -> bytes:
        path = pynng.ffi.string(cast("cffi.FFI.CData", self._mem.sa_path))
        return path if isinstance(path, bytes) else path.encode()

    @property
    def path(self) -> str:
        return self.path_bytes.decode()

    def __str__(self) -> str:
        return self.path


class InAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(self, ffi_sock_addr: cffi.FFI.CData) -> None:
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_in

    @property
    def port(self) -> int:
        """Port, big-endian style"""
        return int(self._mem.sa_port)

    @property
    def addr(self) -> int:
        """IP address as big-endian 32-bit number"""
        return int(self._mem.sa_addr)

    def __str__(self) -> str:
        as_bytes = struct.pack("I", self.addr)
        ip = socket.inet_ntop(socket.AF_INET, as_bytes)
        port = socket.ntohs(self.port)
        return f"{ip}:{port}"


class In6Addr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(self, ffi_sock_addr: cffi.FFI.CData) -> None:
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_in6

    @property
    def port(self) -> int:
        """Port, big-endian style"""
        return int(self._mem.sa_port)

    @property
    def addr(self) -> bytes:
        """IP address as big-endian bytes"""
        return bytes(self._mem.sa_addr)

    def __str__(self) -> str:
        # TODO: not a good string repr at all
        ip = socket.inet_ntop(socket.AF_INET6, self.addr)
        port = socket.ntohs(self.port)
        return f"[{ip}]:{port}"


class ZTAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(self, ffi_sock_addr: cffi.FFI.CData) -> None:
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = cast("_nng.nng_sockaddr", self.sock_addr).s_zt

    @property
    def nwid(self) -> int:
        return int(getattr(self._mem, "as_nwid"))

    @property
    def nodeid(self) -> int:
        return int(getattr(self._mem, "as_nodeid"))

    @property
    def port(self) -> int:
        return int(getattr(self._mem, "as_port"))


class AbstractAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(self, ffi_sock_addr: cffi.FFI.CData) -> None:
        super().__init__(ffi_sock_addr)
        # union member
        self._mem = self.sock_addr.s_abstract

    @property
    def family_as_str(self) -> str:
        return "abstract"

    @property
    def name_bytes(self) -> bytes:
        # Get the length of the name from sa_len
        name_len = self._mem.sa_len
        # Return the raw bytes of the name (up to name_len)
        return bytes(self._mem.sa_name[0:name_len])

    @property
    def name(self) -> str:
        # Decode the name bytes, handling any URI encoding
        name_bytes = self.name_bytes
        try:
            # Try to decode as UTF-8 first
            name_str = name_bytes.decode("utf-8")
            # Unescape any URI-encoded characters
            return urllib.parse.unquote(name_str)
        except UnicodeDecodeError:
            # If UTF-8 decoding fails, return a representation of the bytes
            return repr(name_bytes)

    def __str__(self) -> str:
        # Return the abstract socket URI format
        try:
            # Try to encode as UTF-8 and URI-encode
            name_str = self.name_bytes.decode("utf-8")
            encoded_name = urllib.parse.quote(name_str)
            return f"abstract://{encoded_name}"
        except UnicodeDecodeError:
            # If UTF-8 encoding fails, use a hex representation
            hex_name = self.name_bytes.hex()
            return f"abstract://{hex_name}"


def _nng_sockaddr(
    sa: cffi.FFI.CData, *, lib: _nng._Lib | _nng_v2._Lib | None = None
) -> SockAddr:
    # ensures the correct class gets instantiated based on s_family
    _lib = lib if lib is not None else pynng.lib
    lookup: dict[int, type[SockAddr]] = {
        _lib.NNG_AF_INPROC: InprocAddr,
        _lib.NNG_AF_IPC: IPCAddr,
        _lib.NNG_AF_INET: InAddr,
        _lib.NNG_AF_INET6: In6Addr,
        _lib.NNG_AF_ABSTRACT: AbstractAddr,
    }
    if hasattr(_lib, "NNG_AF_ZT"):
        lookup[int(getattr(_lib, "NNG_AF_ZT"))] = ZTAddr
    # fall through to SockAddr, e.g. if it's unspecified
    sock_addr = cast("_nng.nng_sockaddr | _nng_v2.nng_sockaddr", sa[0])
    cls = lookup.get(sock_addr.s_family, SockAddr)
    return cls(sa)
