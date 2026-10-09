"""Shared test fixtures and configuration for pynng tests."""
import itertools
import pytest

# Thread-safe address counter (itertools.count is implemented in C and atomic)
_addr_counter = itertools.count()


def random_addr():
    """Generate a unique inproc address to prevent test interference."""
    return f"inproc://test-{next(_addr_counter)}"


# Keep backward compatible aliases
_unique_inproc_addr = random_addr
unique_inproc_addr = random_addr

# Standard timeout values (ms) to prevent infinite hangs.
# Tests that intentionally trigger timeouts use SHORT_TIMEOUT.
SHORT_TIMEOUT = 50      # For tests that expect a timeout to fire
FAST_TIMEOUT = 500      # For inproc operations
MEDIUM_TIMEOUT = 3000   # For TCP/IPC operations
SLOW_TIMEOUT = 10000    # For TLS and slow protocols


def _v2_available():
    """Check whether the v2 CFFI extension is importable."""
    try:
        import pynng._nng_v2  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture(params=[
    "v1",
    pytest.param("v2", marks=pytest.mark.nng_v2),
])
def nng(request):
    """Provide either ``pynng`` (v1) or ``pynng.v2`` module.

    Tests using this fixture run once per version. The v2 parametrization
    is skipped when the ``_nng_v2`` extension is not installed.
    """
    if request.param == "v2":
        pytest.importorskip("pynng._nng_v2")
        import pynng.v2 as mod
        return mod
    else:
        import pynng as mod
        return mod


@pytest.fixture
def inproc_addr():
    """Return a unique inproc address for the current test."""
    return random_addr()
