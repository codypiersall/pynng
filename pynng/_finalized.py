"""Check whether NNG runtime has been finalized without performing any dynamic imports."""

import sys


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
