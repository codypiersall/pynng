"""Runtime statistics interface for pynng using NNG statistics API."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional

from ._base import Socket, _resolve_socket
from ._nng import ffi, lib
from .exceptions import check_err


_STAT_TYPE_NAMES = {
    lib.NNG_STAT_SCOPE: "scope",
    lib.NNG_STAT_LEVEL: "level",
    lib.NNG_STAT_COUNTER: "counter",
    lib.NNG_STAT_STRING: "string",
    lib.NNG_STAT_BOOLEAN: "boolean",
    lib.NNG_STAT_ID: "id",
}

_STAT_UNIT_NAMES = {
    lib.NNG_UNIT_NONE: "none",
    lib.NNG_UNIT_BYTES: "bytes",
    lib.NNG_UNIT_MESSAGES: "messages",
    lib.NNG_UNIT_MILLIS: "millis",
    lib.NNG_UNIT_EVENTS: "events",
}


@dataclass(slots=True)
class Stat(Mapping):
    """A structured representation of an NNG runtime statistic.

    Supports both attribute access (e.g. ``stat.value``) and mapping/dict
    access (e.g. ``stat['value']``).
    """

    name: str
    desc: str
    type: int
    unit: int
    value: Any
    timestamp: int
    type_name: str
    unit_name: str
    children: list["Stat"] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        # Allow looking up direct child by name
        for child in self.children:
            if child.name == key:
                return child
        raise KeyError(key)

    def __iter__(self):
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

    def as_dict(self) -> dict[str, Any]:
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

    def find(self, name: str) -> Optional["Stat"]:
        """Find the first stat with matching ``name`` in this tree."""
        if self.name == name:
            return self
        for child in self.children:
            found = child.find(name)
            if found is not None:
                return found
        return None

    def find_all(self, name: str) -> list["Stat"]:
        """Find all stats with matching ``name`` in this tree."""
        results = []
        if self.name == name:
            results.append(self)
        for child in self.children:
            results.extend(child.find_all(name))
        return results


def _extract_stat_value(st, st_type, _lib=lib, _ffi=ffi):
    if st_type in (_lib.NNG_STAT_LEVEL, _lib.NNG_STAT_COUNTER, _lib.NNG_STAT_ID):
        return _lib.nng_stat_value(st)
    elif st_type == _lib.NNG_STAT_STRING:
        c_str = _lib.nng_stat_string(st)
        if c_str == _ffi.NULL:
            return ""
        return _ffi.string(c_str).decode("utf-8", "replace")
    elif st_type == _lib.NNG_STAT_BOOLEAN:
        return bool(_lib.nng_stat_bool(st))
    return None


def _build_stat_node(st, _lib=lib, _ffi=ffi) -> Stat:
    name_p = _lib.nng_stat_name(st)
    desc_p = _lib.nng_stat_desc(st)
    name = _ffi.string(name_p).decode("utf-8", "replace") if name_p != _ffi.NULL else ""
    desc = _ffi.string(desc_p).decode("utf-8", "replace") if desc_p != _ffi.NULL else ""
    st_type = _lib.nng_stat_type(st)
    st_unit = _lib.nng_stat_unit(st)
    val = _extract_stat_value(st, st_type, _lib=_lib, _ffi=_ffi)
    ts = _lib.nng_stat_timestamp(st)

    children = []
    child = _lib.nng_stat_child(st)
    while child != _ffi.NULL:
        children.append(_build_stat_node(child, _lib=_lib, _ffi=_ffi))
        child = _lib.nng_stat_next(child)

    return Stat(
        name=name,
        desc=desc,
        type=st_type,
        unit=st_unit,
        value=val,
        timestamp=ts,
        type_name=_STAT_TYPE_NAMES.get(st_type, "unknown"),
        unit_name=_STAT_UNIT_NAMES.get(st_unit, "unknown"),
        children=children,
    )


def stats() -> Stat:
    """Retrieve a snapshot of all runtime statistics in the process.

    Returns:
        Stat: Root node of the statistics tree.
    """
    return _stats(lib, ffi)


def _stats(_lib, _ffi) -> Stat:
    stat_p = _ffi.new("nng_stat **")
    check_err(_lib.nng_stats_get(stat_p), lib=_lib, ffi=_ffi)
    root = stat_p[0]
    try:
        return _build_stat_node(root, _lib=_lib, _ffi=_ffi)
    finally:
        _lib.nng_stats_free(root)


def socket_stats(sock) -> Optional[Stat]:
    """Retrieve runtime statistics for a specific socket.

    Args:
        sock: A :class:`~pynng.Socket` instance or an ``nng_socket`` handle.

    Returns:
        Stat: The socket's stat subtree, or None if not found.
    """
    return _socket_stats(sock, lib, ffi)


def _socket_stats(sock, default_lib, default_ffi):
    if not isinstance(sock, Socket):
        sock = getattr(sock, "socket", sock)
    _lib, _ffi, nng_sock = _resolve_socket(sock, default_lib, default_ffi)
    stat_p = _ffi.new("nng_stat **")
    check_err(_lib.nng_stats_get(stat_p), lib=_lib, ffi=_ffi)
    root = stat_p[0]
    try:
        s_stat = _lib.nng_stat_find_socket(root, nng_sock)
        if s_stat == _ffi.NULL:
            return None
        return _build_stat_node(s_stat, _lib=_lib, _ffi=_ffi)
    finally:
        _lib.nng_stats_free(root)
