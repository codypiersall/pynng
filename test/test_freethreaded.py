"""Tests for free-threaded Python (PEP 703 / GIL disabled)."""

import os
import sys
import sysconfig
import threading
import time

import pynng
from _test_util import wait_pipe_len


def test_gil_disabled_indicator():
    """Verify whether GIL is disabled (informational on standard Python, verified on freethreaded)."""
    try:
        import pynng.v2  # noqa: F401
    except ImportError:
        pass
    is_gil_enabled = getattr(sys, "_is_gil_enabled", lambda: True)()
    assert isinstance(is_gil_enabled, bool)
    if (
        sysconfig.get_config_var("Py_GIL_DISABLED") == 1
        and os.environ.get("PYTHON_GIL") != "1"
    ):
        assert is_gil_enabled is False


def test_concurrent_multithreaded_pubsub():
    """Stress test concurrent publisher and subscriber threads without GIL synchronization."""
    address = "inproc://freethreaded_pubsub"
    n_messages = 500
    n_publishers = 4

    with pynng.Pub0(listen=address) as pub:
        with pynng.Sub0(dial=address, recv_timeout=2000) as sub:
            sub.subscribe(b"")
            wait_pipe_len(pub, 1)
            wait_pipe_len(sub, 1)

            received = []
            errors = []
            recv_lock = threading.Lock()
            stop_event = threading.Event()

            def subscriber_worker():
                try:
                    while not stop_event.is_set():
                        try:
                            msg = sub.recv()
                            with recv_lock:
                                received.append(msg)
                        except pynng.Timeout:
                            pass
                except BaseException as exc:
                    with recv_lock:
                        errors.append(exc)

            def publisher_worker(pub_id):
                try:
                    for i in range(n_messages):
                        pub.send(f"p{pub_id}-{i}".encode())
                except BaseException as exc:
                    with recv_lock:
                        errors.append(exc)

            sub_thread = threading.Thread(target=subscriber_worker)
            sub_thread.start()

            pub_threads = [
                threading.Thread(target=publisher_worker, args=(p,))
                for p in range(n_publishers)
            ]
            for t in pub_threads:
                t.start()
            for t in pub_threads:
                t.join()

            # Allow remaining in-flight messages to drain
            time.sleep(0.1)
            stop_event.set()
            sub_thread.join()

            assert errors == []
            with recv_lock:
                count = len(received)
            # Pub/sub may drop if buffer fills, but must never crash or corrupt memory
            assert count > 0


def test_concurrent_context_state_machines():
    """Verify multiple threads safely driving separate contexts on a single socket."""
    address = "inproc://freethreaded_contexts"
    with pynng.Rep0(listen=address, recv_timeout=200) as rep, pynng.Req0(
        dial=address, recv_timeout=2000
    ) as req:
        wait_pipe_len(rep, 1)
        wait_pipe_len(req, 1)
        n_contexts = 8
        n_requests_per_ctx = 20
        stop_event = threading.Event()
        errors = []
        err_lock = threading.Lock()

        def rep_worker(ctx):
            try:
                while not stop_event.is_set():
                    try:
                        msg = ctx.recv()
                        ctx.send(msg + b"-ack")
                    except pynng.Timeout:
                        pass
            except BaseException as exc:
                with err_lock:
                    errors.append(exc)

        def req_worker(ctx, worker_id):
            try:
                for i in range(n_requests_per_ctx):
                    data = f"req-{worker_id}-{i}".encode()
                    ctx.send(data)
                    reply = ctx.recv()
                    assert reply == data + b"-ack"
            except BaseException as exc:
                with err_lock:
                    errors.append(exc)

        rep_contexts = [rep.new_context() for _ in range(n_contexts)]
        req_contexts = [req.new_context() for _ in range(n_contexts)]
        try:
            rep_threads = [
                threading.Thread(target=rep_worker, args=(ctx,))
                for ctx in rep_contexts
            ]
            req_threads = [
                threading.Thread(target=req_worker, args=(ctx, idx))
                for idx, ctx in enumerate(req_contexts)
            ]

            for t in rep_threads + req_threads:
                t.start()
            for t in req_threads:
                t.join()
            stop_event.set()
            for t in rep_threads:
                t.join()

            assert errors == []
        finally:
            for ctx in req_contexts + rep_contexts:
                ctx.close()
