"""Shared test fixtures and configuration for pynng tests."""
import itertools

# Thread-safe address counter (itertools.count is implemented in C and atomic)
_addr_counter = itertools.count()


def random_addr():
    """Generate a unique inproc address to prevent test interference."""
    return f"inproc://test-{next(_addr_counter)}"


# Standard timeout values (ms) to prevent infinite hangs.
# Tests that intentionally trigger timeouts use SHORT_TIMEOUT.
SHORT_TIMEOUT = 50      # For tests that expect a timeout to fire
FAST_TIMEOUT = 500      # For inproc operations
MEDIUM_TIMEOUT = 3000   # For TCP/IPC operations
SLOW_TIMEOUT = 10000    # For TLS and slow protocols
