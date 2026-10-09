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


def _probe_tls(module):
    """Check whether TLS support is compiled into an nng library.

    Attempts to listen on tls+tcp://. NNG returns NNG_ENOTSUP immediately
    if TLS was not compiled in. Any other error (e.g. missing TLS config)
    means the TLS transport IS available.
    """
    try:
        s = module.Pair0()
        try:
            s.listen("tls+tcp://127.0.0.1:0")
        except module.NotSupported:
            return False
        except Exception:
            return True
        finally:
            s.close()
        return True
    except Exception:
        return False


def _v1_tls_available():
    try:
        import pynng
        return _probe_tls(pynng)
    except ImportError:
        return False


def _v2_tls_available():
    try:
        import pynng.v2
        return _probe_tls(pynng.v2)
    except ImportError:
        return False


_V1_HAS_TLS = _v1_tls_available()
_V2_HAS_TLS = _v2_tls_available()


def pytest_collection_modifyitems(config, items):
    """xfail TLS tests when TLS is not available for their nng version."""
    for item in items:
        if "requires_tls" not in item.keywords:
            continue

        # Determine which version this test targets
        is_v1 = "nng_v1" in item.keywords or item.nodeid.endswith("[v1]")
        is_v2 = "nng_v2" in item.keywords or item.nodeid.endswith("[v2]")

        if is_v1 and not _V1_HAS_TLS:
            item.add_marker(pytest.mark.xfail(
                reason="v1 TLS not available (engine not supported or PYNNG_TLS_ENGINE=none)",
                raises=Exception,
                strict=True,
            ))
        elif is_v2 and not _V2_HAS_TLS:
            item.add_marker(pytest.mark.xfail(
                reason="v2 TLS not available (engine not supported or PYNNG_TLS_ENGINE=none)",
                raises=Exception,
                strict=True,
            ))
        elif not is_v1 and not is_v2 and not _V1_HAS_TLS and not _V2_HAS_TLS:
            # Unversioned TLS test, neither version has TLS
            item.add_marker(pytest.mark.xfail(
                reason="TLS not available (PYNNG_TLS_ENGINE=none)",
                raises=Exception,
                strict=True,
            ))


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
