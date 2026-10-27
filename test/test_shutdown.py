import subprocess
import sys

import pytest

import pynng


def test_default_nng_fini_at_exit_is_false():
    """Verify that nng_fini_at_exit defaults to False to prevent GC race conditions."""
    assert pynng.nng_fini_at_exit is False
    assert callable(pynng.nng_fini)


def test_shutdown_and_gc_safety_in_subprocess(tmp_path):
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
    return s0, s1, ctx, aio

s0, s1, ctx, aio = asyncio.run(main())
# Trigger finalization
pynng.nng_fini()
# Trigger garbage collection/destruction of remaining objects
del aio
del ctx
del s1
del s0
print("SHUTDOWN_OK")
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "SHUTDOWN_OK" in proc.stdout
    assert "panic" not in proc.stderr.lower()


def test_v2_shutdown_and_gc_safety_in_subprocess(tmp_path):
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
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "V2_SHUTDOWN_OK" in proc.stdout
    assert "panic" not in proc.stderr.lower()


@pytest.mark.parametrize(
    "setting, finalized",
    [
        ("", False),
        ("pynng.nng_fini_at_exit = True", True),
    ],
)
def test_nng_fini_at_exit_controls_finalization_at_exit(tmp_path, setting, finalized):
    """Setting pynng.nng_fini_at_exit decides whether the atexit handler
    calls nng_fini()."""
    code = f"""
import atexit

def report():
    import pynng.nng
    print("finalized:", pynng.nng._finalized)

# Registered before pynng's handler, so it runs after it.
atexit.register(report)

import pynng

{setting}
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert (proc.returncode, proc.stdout, proc.stderr) == (
        0,
        f"finalized: {finalized}\n",
        "",
    )
