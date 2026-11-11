"""Runtime statistics interface for pynng using nng statistics API."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias, cast

from ._base import Socket, _resolve_socket
from ._nng import ffi, lib
from .exceptions import check_err

if TYPE_CHECKING:
    import cffi

    from . import _nng, _nng_v2

    class _NngStat(_nng.nng_stat, _nng_v2.nng_stat):
        pass

    class _NngSocket(_nng.nng_socket, _nng_v2.nng_socket):
        pass


StatValue: TypeAlias = "int | str | bool | None | Stat | list[Stat]"
StatDict: TypeAlias = "dict[str, int | str | bool | None | list[StatDict]]"


def _stat_type_name(st_type: int, _lib: _nng._Lib | _nng_v2._Lib = lib) -> str:
    return {
        int(_lib.NNG_STAT_SCOPE): "scope",
        int(_lib.NNG_STAT_LEVEL): "level",
        int(_lib.NNG_STAT_COUNTER): "counter",
        int(_lib.NNG_STAT_STRING): "string",
        int(_lib.NNG_STAT_BOOLEAN): "boolean",
        int(_lib.NNG_STAT_ID): "id",
    }.get(st_type, "unknown")


def _stat_unit_name(st_unit: int, _lib: _nng._Lib | _nng_v2._Lib = lib) -> str:
    return {
        int(_lib.NNG_UNIT_NONE): "none",
        int(_lib.NNG_UNIT_BYTES): "bytes",
        int(_lib.NNG_UNIT_MESSAGES): "messages",
        int(_lib.NNG_UNIT_MILLIS): "millis",
        int(_lib.NNG_UNIT_EVENTS): "events",
    }.get(st_unit, "unknown")


@dataclass(slots=True)
class Stat(Mapping[str, StatValue]):
    """A structured representation of an nng runtime statistic.

    Supports both attribute access (e.g. ``stat.value``) and mapping/dict
    access (e.g. ``stat['value']``).
    """

    name: str
    desc: str
    type: int
    unit: int
    value: int | str | bool | None
    timestamp: int
    type_name: str
    unit_name: str
    children: list[Stat] = field(default_factory=list)

    def __getitem__(self, key: str) -> StatValue:
        if hasattr(self, key):
            return cast(StatValue, getattr(self, key))
        # Allow looking up direct child by name
        for child in self.children:
            if child.name == key:
                return child
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(
            (
                "name",
                "desc",
                "type",
                "unit",
                "value",
                "timestamp",
                "type_name",
                "unit_name",
                "children",
            )
        )

    def __len__(self) -> int:
        return 9

    def as_dict(self) -> StatDict:
        """Convert this Stat and all its children into a pure Python dictionary."""
        return {
            "name": self.name,
            "desc": self.desc,
            "type": self.type,
            "unit": self.unit,
            "value": self.value,
            "timestamp": self.timestamp,
            "type_name": self.type_name,
            "unit_name": self.unit_name,
            "children": [ch.as_dict() for ch in self.children],
        }

    to_dict = as_dict

    def find(self, name: str) -> Stat | None:
        """Find the first stat with matching ``name`` in this tree."""
        if self.name == name:
            return self
        for child in self.children:
            found = child.find(name)
            if found is not None:
                return found
        return None

    def find_all(self, name: str) -> list[Stat]:
        """Find all stats with matching ``name`` in this tree."""
        results: list[Stat] = []
        if self.name == name:
            results.append(self)
        for child in self.children:
            results.extend(child.find_all(name))
        return results


def _extract_stat_value(
    st: _nng.nng_stat | _nng_v2.nng_stat,
    st_type: int,
    _lib: _nng._Lib | _nng_v2._Lib = lib,
    _ffi: cffi.FFI = ffi,
) -> int | str | bool | None:
    st_compat = cast("_NngStat", st)
    if st_type in (_lib.NNG_STAT_LEVEL, _lib.NNG_STAT_COUNTER, _lib.NNG_STAT_ID):
        return int(_lib.nng_stat_value(st_compat))
    elif st_type == _lib.NNG_STAT_STRING:
        c_str = cast("cffi.FFI.CData", _lib.nng_stat_string(st_compat))
        if c_str == _ffi.NULL:
            return ""
        raw = _ffi.string(c_str)
        return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    elif st_type == _lib.NNG_STAT_BOOLEAN:
        return bool(_lib.nng_stat_bool(st_compat))
    return None


def _build_stat_node(
    st: _nng.nng_stat | _nng_v2.nng_stat,
    _lib: _nng._Lib | _nng_v2._Lib = lib,
    _ffi: cffi.FFI = ffi,
) -> Stat:
    st_compat = cast("_NngStat", st)
    name_p = cast("cffi.FFI.CData", _lib.nng_stat_name(st_compat))
    desc_p = cast("cffi.FFI.CData", _lib.nng_stat_desc(st_compat))
    if name_p != _ffi.NULL:
        raw_name = _ffi.string(name_p)
        name = (
            raw_name.decode("utf-8", "replace")
            if isinstance(raw_name, bytes)
            else str(raw_name)
        )
    else:
        name = ""
    if desc_p != _ffi.NULL:
        raw_desc = _ffi.string(desc_p)
        desc = (
            raw_desc.decode("utf-8", "replace")
            if isinstance(raw_desc, bytes)
            else str(raw_desc)
        )
    else:
        desc = ""
    st_type = int(_lib.nng_stat_type(st_compat))
    st_unit = int(_lib.nng_stat_unit(st_compat))
    val = _extract_stat_value(st_compat, st_type, _lib=_lib, _ffi=_ffi)
    ts = int(_lib.nng_stat_timestamp(st_compat))

    children: list[Stat] = []
    child = _lib.nng_stat_child(st_compat)
    while cast("cffi.FFI.CData", child) != _ffi.NULL:
        children.append(_build_stat_node(child, _lib=_lib, _ffi=_ffi))
        child = _lib.nng_stat_next(cast("_NngStat", child))

    return Stat(
        name=name,
        desc=desc,
        type=st_type,
        unit=st_unit,
        value=val,
        timestamp=ts,
        type_name=_stat_type_name(st_type, _lib),
        unit_name=_stat_unit_name(st_unit, _lib),
        children=children,
    )


def stats() -> Stat:
    """Retrieve a snapshot of all runtime statistics in the process.

    Returns:
        Stat: Root node of the statistics tree.
    """
    return _stats(lib, ffi)


def _stats(_lib: _nng._Lib | _nng_v2._Lib, _ffi: cffi.FFI) -> Stat:
    stat_p = _ffi.new("nng_stat **")
    check_err(_lib.nng_stats_get(stat_p), lib=_lib, ffi=_ffi)
    root = cast("_NngStat", stat_p[0])
    try:
        return _build_stat_node(root, _lib=_lib, _ffi=_ffi)
    finally:
        _lib.nng_stats_free(root)


def socket_stats(
    sock: Socket | _nng.nng_socket | _nng_v2.nng_socket | cffi.FFI.CData,
) -> Stat | None:
    """Retrieve runtime statistics for a specific socket.

    Args:
        sock: A :class:`~pynng.Socket` instance or an ``nng_socket`` handle.

    Returns:
        Stat: The socket's stat subtree, or None if not found.
    """
    return _socket_stats(sock, lib, ffi)


def _socket_stats(
    sock: Socket | _nng.nng_socket | _nng_v2.nng_socket | cffi.FFI.CData,
    default_lib: _nng._Lib | _nng_v2._Lib,
    default_ffi: cffi.FFI,
) -> Stat | None:
    if not isinstance(sock, Socket):
        sock = getattr(sock, "socket", sock)
    _lib, _ffi, nng_sock = _resolve_socket(sock, default_lib, default_ffi)
    stat_p = _ffi.new("nng_stat **")
    check_err(_lib.nng_stats_get(stat_p), lib=_lib, ffi=_ffi)
    root = cast("_NngStat", stat_p[0])
    try:
        s_stat = _lib.nng_stat_find_socket(root, cast("_NngSocket", nng_sock))
        if cast("cffi.FFI.CData", s_stat) == _ffi.NULL:
            return None
        return _build_stat_node(s_stat, _lib=_lib, _ffi=_ffi)
    finally:
        _lib.nng_stats_free(root)
