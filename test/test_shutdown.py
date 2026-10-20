import subprocess
import sys

import pynng


def test_default_nng_fini_at_exit_is_false():
    """Verify that nng_fini_at_exit defaults to False to prevent GC race conditions."""
    assert pynng.nng_fini_at_exit is False
    assert callable(pynng.nng_fini)


def test_shutdown_and_gc_safety_in_subprocess():
    """Verify that calling nng_fini() before GC does not crash or panic the process."""
    code = """
import asyncio
import pynng
from pynng._aio import AIOHelper

async def main():
    s0 = pynng.Pair0()
    s1 = pynng.Req0()
    ctx = s1.new_context()
    aio = AIOHelper(s0, async_backend="asyncio")
    # Trigger finalization
    pynng.nng_fini()
    # Trigger garbage collection/destruction of remaining objects
    del aio
    del ctx
    del s1
    del s0

asyncio.run(main())
print("SHUTDOWN_OK")
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "SHUTDOWN_OK" in proc.stdout
    assert "panic" not in proc.stderr.lower()


def test_v2_shutdown_and_gc_safety_in_subprocess():
    """Verify that v2 nng_fini() does not cause crashes during subsequent GC."""
    code = """
import pynng.v2 as v2

s = v2.Pair0()
v2.nng_fini()
del s
print("V2_SHUTDOWN_OK")
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "V2_SHUTDOWN_OK" in proc.stdout
    assert "panic" not in proc.stderr.lower()
