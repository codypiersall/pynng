"""Check whether nng runtime has been finalized without performing any dynamic imports."""

from __future__ import annotations

import collections
import sys
import threading

# Retain closed sockets and pointer options (e.g. TLSConfig) in a FIFO buffer
# so that nng background reaper threads (tls_reap, listener_reap, dialer_reap)
# finish tearing down C-level mbedTLS structures before Python GC finalizes them.
_RETAIN_CLOSED_MAX = 64
_closed_objects_retained: collections.deque[object] = collections.deque(
    maxlen=_RETAIN_CLOSED_MAX
)
_closed_objects_lock = threading.Lock()


def retain_closed(obj: object) -> None:
    """Retain a reference to an object in the closed objects buffer."""
    if obj is not None:
        with _closed_objects_lock:
            _closed_objects_retained.append(obj)


def is_nng_finalized(lib: object = None) -> bool:
    """Return True if the specified nng runtime (or any runtime when lib is None) has been finalized.

    Safe to call from __del__ and GC finalizers because it performs no imports,
    allocates no new module structures, and relies solely on sys.modules lookup.
    """
    v1_nng_mod = sys.modules.get("pynng.nng")
    v1_mod = sys.modules.get("pynng")
    v2_nng_mod = sys.modules.get("pynng.v2.nng")
    v2_mod = sys.modules.get("pynng.v2")

    if lib is not None:
        v2_lib = getattr(v2_nng_mod, "lib", None) or getattr(v2_mod, "lib", None)
        if v2_lib is not None and lib is v2_lib:
            return bool(
                (v2_nng_mod is not None and getattr(v2_nng_mod, "_finalized", False))
                or (v2_mod is not None and getattr(v2_mod, "_finalized", False))
            )
        v1_lib = getattr(v1_nng_mod, "lib", None) or getattr(v1_mod, "lib", None)
        if v1_lib is not None and lib is v1_lib:
            return bool(
                (v1_nng_mod is not None and getattr(v1_nng_mod, "_finalized", False))
                or (v1_mod is not None and getattr(v1_mod, "_finalized", False))
            )

    if v1_nng_mod is not None and getattr(v1_nng_mod, "_finalized", False):
        return True
    if v1_mod is not None and getattr(v1_mod, "_finalized", False):
        return True
    if v2_nng_mod is not None and getattr(v2_nng_mod, "_finalized", False):
        return True
    if v2_mod is not None and getattr(v2_mod, "_finalized", False):
        return True
    return False
