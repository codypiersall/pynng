from __future__ import annotations

import os
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

    __slots__ = ("_ffi", "_lib", "_sock_addr")

    type_to_str: dict[int, str] = {
        pynng.lib.NNG_AF_UNSPEC: "Unspecified",
        pynng.lib.NNG_AF_INPROC: "inproc",
        pynng.lib.NNG_AF_IPC: "ipc",
        pynng.lib.NNG_AF_INET: "inet",
        pynng.lib.NNG_AF_INET6: "inetv6",
        pynng.lib.NNG_AF_ZT: "zerotier",
        pynng.lib.NNG_AF_ABSTRACT: "abstract",
    }

    _base_type_to_str: dict[int, str] = {
        pynng.lib.NNG_AF_UNSPEC: "Unspecified",
        pynng.lib.NNG_AF_INPROC: "inproc",
        pynng.lib.NNG_AF_IPC: "ipc",
        pynng.lib.NNG_AF_INET: "inet",
        pynng.lib.NNG_AF_INET6: "inetv6",
    }

    def __init__(
        self,
        ffi_sock_addr: cffi.FFI.CData,
        *,
        ffi: cffi.FFI | None = None,
        lib: _nng._Lib | _nng_v2._Lib | None = None,
    ) -> None:
        self._sock_addr = ffi_sock_addr
        self._ffi: cffi.FFI = ffi if ffi is not None else pynng.ffi
        self._lib: _nng._Lib | _nng_v2._Lib = lib if lib is not None else pynng.lib

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
        fam = self.family
        _lib = self._lib
        if fam == int(_lib.NNG_AF_UNSPEC):
            return "Unspecified"
        if fam == int(_lib.NNG_AF_INPROC):
            return "inproc"
        if fam == int(_lib.NNG_AF_IPC):
            return "ipc"
        if fam == int(_lib.NNG_AF_INET):
            return "inet"
        if fam == int(_lib.NNG_AF_INET6):
            return "inetv6"
        if hasattr(_lib, "NNG_AF_ZT") and fam == int(getattr(_lib, "NNG_AF_ZT")):
            return "zerotier"
        if fam == int(_lib.NNG_AF_ABSTRACT):
            return "abstract"
        return self._base_type_to_str.get(fam, f"unknown ({fam})")

    def __repr__(self) -> str:
        return f"nng_sockaddr {{.family = {self.family}}}"


class InprocAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(
        self,
        ffi_sock_addr: cffi.FFI.CData,
        *,
        ffi: cffi.FFI | None = None,
        lib: _nng._Lib | _nng_v2._Lib | None = None,
    ) -> None:
        super().__init__(ffi_sock_addr, ffi=ffi, lib=lib)
        # union member
        self._mem = self.sock_addr.s_inproc

    @property
    def family_as_str(self) -> str:
        return "inproc"

    @property
    def name_bytes(self) -> bytes:
        name = self._ffi.string(cast("cffi.FFI.CData", self._mem.sa_name))
        return name if isinstance(name, bytes) else name.encode()

    @property
    def name(self) -> str:
        return self.name_bytes.decode("utf-8", "surrogateescape")

    def __str__(self) -> str:
        return self.name


class IPCAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(
        self,
        ffi_sock_addr: cffi.FFI.CData,
        *,
        ffi: cffi.FFI | None = None,
        lib: _nng._Lib | _nng_v2._Lib | None = None,
    ) -> None:
        super().__init__(ffi_sock_addr, ffi=ffi, lib=lib)
        # union member
        self._mem = self.sock_addr.s_ipc

    @property
    def family_as_str(self) -> str:
        return "ipc"

    @property
    def path_bytes(self) -> bytes:
        path = self._ffi.string(cast("cffi.FFI.CData", self._mem.sa_path))
        return path if isinstance(path, bytes) else path.encode()

    @property
    def path(self) -> str:
        return os.fsdecode(self.path_bytes)

    def __str__(self) -> str:
        return self.path


class InAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(
        self,
        ffi_sock_addr: cffi.FFI.CData,
        *,
        ffi: cffi.FFI | None = None,
        lib: _nng._Lib | _nng_v2._Lib | None = None,
    ) -> None:
        super().__init__(ffi_sock_addr, ffi=ffi, lib=lib)
        # union member
        self._mem = self.sock_addr.s_in

    @property
    def family_as_str(self) -> str:
        return "inet"

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

    def __init__(
        self,
        ffi_sock_addr: cffi.FFI.CData,
        *,
        ffi: cffi.FFI | None = None,
        lib: _nng._Lib | _nng_v2._Lib | None = None,
    ) -> None:
        super().__init__(ffi_sock_addr, ffi=ffi, lib=lib)
        # union member
        self._mem = self.sock_addr.s_in6

    @property
    def family_as_str(self) -> str:
        return "inetv6"

    @property
    def port(self) -> int:
        """Port, big-endian style"""
        return int(self._mem.sa_port)

    @property
    def addr(self) -> bytes:
        """IP address as big-endian bytes"""
        return bytes(self._mem.sa_addr)

    def __str__(self) -> str:
        ip = socket.inet_ntop(socket.AF_INET6, self.addr)
        port = socket.ntohs(self.port)
        return f"[{ip}]:{port}"


class ZTAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(
        self,
        ffi_sock_addr: cffi.FFI.CData,
        *,
        ffi: cffi.FFI | None = None,
        lib: _nng._Lib | _nng_v2._Lib | None = None,
    ) -> None:
        super().__init__(ffi_sock_addr, ffi=ffi, lib=lib)
        # union member
        self._mem = cast("_nng.nng_sockaddr", self.sock_addr).s_zt

    @property
    def family_as_str(self) -> str:
        return "zerotier"

    @property
    def nwid(self) -> int:
        return int(self._mem.sa_nwid)

    @property
    def nodeid(self) -> int:
        return int(self._mem.sa_nodeid)

    @property
    def port(self) -> int:
        return int(self._mem.sa_port)

    def __str__(self) -> str:
        return f"zt://{self.nodeid:010x}.{self.nwid:016x}:{self.port}"


class AbstractAddr(SockAddr):
    __slots__ = ("_mem",)

    def __init__(
        self,
        ffi_sock_addr: cffi.FFI.CData,
        *,
        ffi: cffi.FFI | None = None,
        lib: _nng._Lib | _nng_v2._Lib | None = None,
    ) -> None:
        super().__init__(ffi_sock_addr, ffi=ffi, lib=lib)
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
        # Decode the raw name bytes (sa_name is already unescaped in C by NNG)
        return self.name_bytes.decode("utf-8", "surrogateescape")

    def __str__(self) -> str:
        # Return the abstract socket URI format using quote_from_bytes on raw bytes
        encoded_name = urllib.parse.quote_from_bytes(self.name_bytes)
        return f"abstract://{encoded_name}"


def _nng_sockaddr(
    sa: cffi.FFI.CData,
    *,
    lib: _nng._Lib | _nng_v2._Lib | None = None,
    ffi: cffi.FFI | None = None,
) -> SockAddr:
    # ensures the correct class gets instantiated based on s_family
    _lib = lib if lib is not None else pynng.lib
    _ffi = ffi if ffi is not None else pynng.ffi
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
    return cls(sa, ffi=_ffi, lib=_lib)
