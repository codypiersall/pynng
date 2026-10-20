"""
Tests for interruptable synchronous receive operations.

Verifies that sock.recv(), sock.recv_msg(), sock.recv_into(), and Context.recv_msg()
can be interrupted by SIGINT (such as Ctrl-C) instead of hanging indefinitely
in C-level blocking calls (e.g. pthread_cond_wait).
"""

import os
import signal
import subprocess
import sys
import time

import pytest

import pynng


def _run_subprocess_and_interrupt(snippet, timeout=3.0):
    """Run a Python snippet in a child process, wait for READY, send SIGINT,

    and verify it catches KeyboardInterrupt.
    """
    code = f"""
import sys
{snippet}
"""
    import tempfile

    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=tempfile.gettempdir(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Wait for child to reach blocking call
    ready_line = proc.stdout.readline().strip()
    assert ready_line == "READY"

    # Give child process time to enter nng_aio_wait in the sliced loop
    time.sleep(0.15)

    # Send SIGINT (Ctrl-C equivalent)
    proc.send_signal(signal.SIGINT)

    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail(f"Child process hung after SIGINT, failed to interrupt:\n{code}")

    assert "INTERRUPTED" in out, f"Child did not report INTERRUPTED. Out: {out}, Err: {err}"
    assert proc.returncode == 0, f"Child exited with non-zero code {proc.returncode}. Err: {err}"


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT subprocess testing requires POSIX")
def test_sock_recv_interrupted_by_sigint():
    snippet = """
import pynng

s = pynng.Pair0()
try:
    print("READY", flush=True)
    s.recv()
except KeyboardInterrupt:
    print("INTERRUPTED", flush=True)
finally:
    s.close()
"""
    _run_subprocess_and_interrupt(snippet)


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT subprocess testing requires POSIX")
def test_sock_recv_msg_interrupted_by_sigint():
    snippet = """
import pynng

s = pynng.Pair0()
try:
    print("READY", flush=True)
    s.recv_msg()
except KeyboardInterrupt:
    print("INTERRUPTED", flush=True)
finally:
    s.close()
"""
    _run_subprocess_and_interrupt(snippet)


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT subprocess testing requires POSIX")
def test_sock_recv_into_interrupted_by_sigint():
    snippet = """
import pynng

s = pynng.Pair0()
buf = bytearray(64)
try:
    print("READY", flush=True)
    s.recv_into(buf)
except KeyboardInterrupt:
    print("INTERRUPTED", flush=True)
finally:
    s.close()
"""
    _run_subprocess_and_interrupt(snippet)


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT subprocess testing requires POSIX")
def test_context_recv_msg_interrupted_by_sigint():
    snippet = """
import pynng

s = pynng.Rep0()
ctx = s.new_context()
try:
    print("READY", flush=True)
    ctx.recv_msg()
except KeyboardInterrupt:
    print("INTERRUPTED", flush=True)
finally:
    ctx.close()
    s.close()
"""
    _run_subprocess_and_interrupt(snippet)


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT subprocess testing requires POSIX")
def test_v2_sock_recv_interrupted_by_sigint():
    snippet = """
import pynng.v2

s = pynng.v2.Pair0()
try:
    print("READY", flush=True)
    s.recv()
except KeyboardInterrupt:
    print("INTERRUPTED", flush=True)
finally:
    s.close()
"""
    _run_subprocess_and_interrupt(snippet)


def test_sock_recv_timeout_honored():
    with pynng.Pair0() as s:
        s.recv_timeout = 150
        t0 = time.monotonic()
        with pytest.raises(pynng.Timeout):
            s.recv()
        elapsed = time.monotonic() - t0
        # Should have waited approximately 150ms
        assert 0.12 <= elapsed <= 0.60


def test_sock_recv_zero_timeout():
    with pynng.Pair0() as s:
        s.recv_timeout = 0
        with pytest.raises(pynng.Timeout):
            s.recv()


def test_sock_recv_nonblocking():
    with pynng.Pair0() as s:
        with pytest.raises(pynng.TryAgain):
            s.recv(block=False)
        with pytest.raises(pynng.TryAgain):
            s.recv_msg(block=False)


def test_sock_recv_roundtrip_data_integrity():
    addr = "inproc://test-interruptable-roundtrip"
    with pynng.Pair0(listen=addr) as s1, pynng.Pair0(dial=addr) as s2:
        # Standard payload
        s2.send(b"hello world")
        assert s1.recv() == b"hello world"

        # Large payload (64 KB)
        large = b"x" * 65536
        s2.send(large)
        assert s1.recv() == large

        # Zero-byte payload
        s2.send(b"")
        assert s1.recv() == b""


def test_sock_recv_into_roundtrip():
    addr = "inproc://test-interruptable-recv-into"
    with pynng.Pair0(listen=addr) as s1, pynng.Pair0(dial=addr) as s2:
        s2.send(b"12345678")
        buf = bytearray(16)
        nbytes = s1.recv_into(buf)
        assert nbytes == 8
        assert buf[:8] == b"12345678"
