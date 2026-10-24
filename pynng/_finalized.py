"""Check whether NNG runtime has been finalized without performing any dynamic imports."""

import collections
import sys
import threading

# Retain closed sockets and pointer options (e.g. TLSConfig) in a FIFO buffer
# so that NNG background reaper threads (tls_reap, listener_reap, dialer_reap)
# finish tearing down C-level mbedTLS structures before Python GC finalizes them.
_RETAIN_CLOSED_MAX = 64
_closed_objects_retained = collections.deque(maxlen=_RETAIN_CLOSED_MAX)
_closed_objects_lock = threading.Lock()


def retain_closed(obj):
    """Retain a reference to an object in the closed objects buffer."""
    if obj is not None:
        with _closed_objects_lock:
            _closed_objects_retained.append(obj)


def is_nng_finalized() -> bool:
    """Return True if nng runtime has been finalized.

    Safe to call from __del__ and GC finalizers because it performs no imports,
    allocates no new module structures, and relies solely on sys.modules lookup.
    """
    mod = sys.modules.get("pynng.nng")
    if mod is not None and getattr(mod, "_finalized", False):
        return True
    v2_mod = sys.modules.get("pynng.v2")
    if v2_mod is not None and getattr(v2_mod, "_finalized", False):
        return True
    return False
