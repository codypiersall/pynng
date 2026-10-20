"""Runtime statistics interface for pynng using NNG statistics API."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional

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


@dataclass
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


def _extract_stat_value(st, st_type):
    if st_type in (lib.NNG_STAT_LEVEL, lib.NNG_STAT_COUNTER, lib.NNG_STAT_ID):
        return lib.nng_stat_value(st)
    elif st_type == lib.NNG_STAT_STRING:
        c_str = lib.nng_stat_string(st)
        return ffi.string(c_str).decode("utf-8", "replace") if c_str != ffi.NULL else ""
    elif st_type == lib.NNG_STAT_BOOLEAN:
        return bool(lib.nng_stat_bool(st))
    return None


def _build_stat_node(st) -> Stat:
    name_p = lib.nng_stat_name(st)
    desc_p = lib.nng_stat_desc(st)
    name = ffi.string(name_p).decode("utf-8", "replace") if name_p != ffi.NULL else ""
    desc = ffi.string(desc_p).decode("utf-8", "replace") if desc_p != ffi.NULL else ""
    st_type = lib.nng_stat_type(st)
    st_unit = lib.nng_stat_unit(st)
    val = _extract_stat_value(st, st_type)
    ts = lib.nng_stat_timestamp(st)

    children = []
    child = lib.nng_stat_child(st)
    while child != ffi.NULL:
        children.append(_build_stat_node(child))
        child = lib.nng_stat_next(child)

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
    stat_p = ffi.new("nng_stat **")
    check_err(lib.nng_stats_get(stat_p))
    root = stat_p[0]
    try:
        return _build_stat_node(root)
    finally:
        lib.nng_stats_free(root)


def socket_stats(sock) -> Optional[Stat]:
    """Retrieve runtime statistics for a specific socket.

    Args:
        sock: A :class:`~pynng.Socket` instance.

    Returns:
        Stat: The socket's stat subtree, or None if not found.
    """
    stat_p = ffi.new("nng_stat **")
    check_err(lib.nng_stats_get(stat_p))
    root = stat_p[0]
    try:
        nng_sock = sock.socket if hasattr(sock, "socket") else sock
        s_stat = lib.nng_stat_find_socket(root, nng_sock)
        if s_stat == ffi.NULL:
            return None
        return _build_stat_node(s_stat)
    finally:
        lib.nng_stats_free(root)
