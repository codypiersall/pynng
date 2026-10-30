import asyncio
import multiprocessing as mp
import os
import subprocess
import sys

import pytest

import pynng


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is only supported on POSIX")
def test_fork_after_init_raises_runtime_error_in_child():
    """Verify that attempting to create a socket in a forked child raises RuntimeError."""
    # Ensure NNG is initialized in parent
    s = pynng.Pair0()
    s.close()

    ctx = mp.get_context("fork")

    def run_child(queue):
        try:
            s2 = pynng.Pair0()
            s2.close()
            queue.put("SUCCESS")
        except RuntimeError as exc:
            queue.put(f"RUNTIME_ERROR: {exc}")
        except BaseException as exc:  # noqa: BLE001
            queue.put(f"UNEXPECTED_EXCEPTION: {type(exc).__name__}: {exc}")

    queue = ctx.Queue()
    proc = ctx.Process(target=run_child, args=(queue,))
    proc.start()
    proc.join(timeout=5)

    assert proc.exitcode == 0
    result = queue.get(timeout=2)
    assert result.startswith("RUNTIME_ERROR")
    assert "does not support fork()" in result
    assert "multiprocessing.set_start_method('spawn')" in result


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is only supported on POSIX")
def test_fork_existing_socket_send_raises_runtime_error():
    """Verify that calling send() on an inherited socket in a forked child raises RuntimeError."""
    s = pynng.Pair0()

    ctx = mp.get_context("fork")

    def run_child(sock, queue):
        try:
            sock.send(b"hello")
            queue.put("SUCCESS")
        except RuntimeError as exc:
            queue.put(f"RUNTIME_ERROR: {exc}")
        except BaseException as exc:  # noqa: BLE001
            queue.put(f"UNEXPECTED_EXCEPTION: {type(exc).__name__}: {exc}")

    queue = ctx.Queue()
    proc = ctx.Process(target=run_child, args=(s, queue))
    proc.start()
    proc.join(timeout=5)
    s.close()

    assert proc.exitcode == 0
    result = queue.get(timeout=2)
    assert result.startswith("RUNTIME_ERROR")
    assert "does not support fork()" in result


def test_spawn_process_succeeds(tmp_path):
    """Verify that multiprocessing with spawn context works properly."""
    script = tmp_path / "spawn_worker.py"
    script.write_text("""
import multiprocessing as mp
import pynng

def worker():
    with pynng.Pair0() as s:
        pass

if __name__ == '__main__':
    with pynng.Pair0() as s:
        pass
    ctx = mp.get_context("spawn")
    p = ctx.Process(target=worker)
    p.start()
    p.join(timeout=5)
    assert p.exitcode == 0
    print("SPAWN_OK")
""")
    res = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "SPAWN_OK" in res.stdout


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is only supported on POSIX")
@pytest.mark.parametrize("on_context", [False, True], ids=["socket", "context"])
@pytest.mark.parametrize("op", ["arecv", "asend_msg"])
def test_fork_inherited_async_operation_raises_runtime_error(op, on_context):
    """Async send and receive on an inherited socket or context raise RuntimeError."""
    sock = pynng.Rep0()
    target = sock.new_context() if on_context else sock
    msg = pynng.Message(b"hello")

    async def run_op():
        if op == "arecv":
            await target.arecv()
        else:
            await target.asend_msg(msg)

    ctx = mp.get_context("fork")

    def run_child(queue):
        try:
            asyncio.run(asyncio.wait_for(run_op(), 2))
            queue.put("SUCCESS")
        except RuntimeError as exc:
            queue.put(f"RUNTIME_ERROR: {exc}")
        except BaseException as exc:  # noqa: BLE001
            queue.put(f"UNEXPECTED_EXCEPTION: {type(exc).__name__}: {exc}")

    queue = ctx.Queue()
    proc = ctx.Process(target=run_child, args=(queue,))
    proc.start()
    proc.join(timeout=10)
    if proc.exitcode is None:
        proc.kill()
        proc.join()
    sock.close()

    assert proc.exitcode == 0
    result = queue.get(timeout=2)
    assert result.startswith("RUNTIME_ERROR")
    assert "does not support fork()" in result


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is only supported on POSIX")
@pytest.mark.parametrize("use_v2", [False, True], ids=["v1", "v2"])
@pytest.mark.parametrize("on_context", [False, True], ids=["socket", "context"])
def test_fork_inherited_send_msg_raises_runtime_error(on_context, use_v2):
    """Synchronous send_msg on an inherited socket or context raises RuntimeError."""
    mod = pynng
    if use_v2:
        mod = pytest.importorskip("pynng.v2")
    sock = mod.Rep0()
    target = sock.new_context() if on_context else sock
    msg = mod.Message(b"hello")

    ctx = mp.get_context("fork")

    def run_child(queue):
        expected = None
        try:
            pynng._base._check_fork()
        except RuntimeError as ref_exc:
            expected = str(ref_exc)
        try:
            target.send_msg(msg)
            queue.put(("SUCCESS", "", expected))
        except RuntimeError as exc:
            queue.put(("RUNTIME_ERROR", str(exc), expected))
        except BaseException as exc:  # noqa: BLE001
            queue.put(("UNEXPECTED_EXCEPTION", f"{type(exc).__name__}: {exc}", expected))

    queue = ctx.Queue()
    proc = ctx.Process(target=run_child, args=(queue,))
    proc.start()
    proc.join(timeout=10)
    if proc.exitcode is None:
        proc.kill()
        proc.join()
    if on_context:
        target.close()
    sock.close()

    assert proc.exitcode == 0
    kind, err_msg, expected_msg = queue.get(timeout=2)
    assert kind == "RUNTIME_ERROR"
    assert expected_msg is not None
    assert err_msg == expected_msg
