"""
Let's test up those pipes
"""


import contextlib
import threading
import time

import pytest

import pynng
import pynng.sockaddr
from _test_util import wait_pipe_len
from conftest import random_addr, FAST_TIMEOUT


def test_pipe_gets_added_and_removed():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        assert len(s0.pipes) == 0
        assert len(s1.pipes) == 0
        s1.dial(addr)
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        # Close one side explicitly and verify pipes are removed on both ends
        # while both sockets are still open (avoids racing against socket
        # teardown, which can be slow on Windows ARM).
        s1.close()
        wait_pipe_len(s0, 0)
        wait_pipe_len(s1, 0)


def test_close_pipe_works():
    addr = random_addr()
    with pynng.Pair0() as s0, pynng.Pair0() as s1:
        # list of pipes that got the callback called on them
        cb_pipes = []

        def cb(pipe):
            cb_pipes.append(pipe)

        # first add callbacks, before listening and dialing.  The callback just adds
        # the pipe to cb_pipes; but this way we can ensure the callback got called.
        s0.add_post_pipe_remove_cb(cb)
        s1.add_post_pipe_remove_cb(cb)
        s0.listen(addr)
        s1.dial(addr)
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        p0 = s0.pipes[0]
        p1 = s1.pipes[0]
        pipe0 = s0.pipes[0]
        pipe0.close()
        # time out in 5 seconds if stuff dosen't work
        timeout = time.monotonic() + 5.0
        while len(cb_pipes) < 2 and time.monotonic() < timeout:
            time.sleep(0.0005)
        if time.monotonic() > timeout:
            raise TimeoutError(
                "Pipe close callbacks were not called; pipe close doesn't work?"
            )
        # we cannot assert the length of cb_pipes is 2 because the sockets might have
        # reconnected in the meantime, so we can only assert that the pipes that
        # *should* have been closed *have* been closed.
        assert p0 in cb_pipes and p1 in cb_pipes


def test_pipe_local_and_remote_addresses():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        p0 = s0.pipes[0]
        p1 = s1.pipes[0]
        local_addr0 = p0.local_address
        remote_addr0 = p0.remote_address
        local_addr1 = p1.local_address
        remote_addr1 = p1.remote_address
        # Verify address types
        assert isinstance(local_addr0, pynng.sockaddr.InprocAddr)
        assert isinstance(remote_addr0, pynng.sockaddr.InprocAddr)
        # Verify symmetry: listener's local == dialer's remote
        assert str(local_addr0) == str(remote_addr1)
        assert str(local_addr1) == str(remote_addr0)
        # Verify the actual address content matches what was listened on
        assert str(local_addr0) == addr


def test_pre_pipe_connect_cb_totally_works():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        called = False

        def pre_connect_cb(_):
            nonlocal called
            called = True

        s0.add_pre_pipe_connect_cb(pre_connect_cb)
        s1.dial(addr)
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        later = time.monotonic() + 10
        while later > time.monotonic():
            if called:
                break
            time.sleep(0.0005)
        assert called


def test_closing_pipe_in_pre_connect_works():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        s0.name = "s0"
        s1.name = "s1"
        pre_connect_cb_was_called = False
        post_connect_cb_was_called = False

        def pre_connect_cb(pipe):
            pipe.close()
            nonlocal pre_connect_cb_was_called
            pre_connect_cb_was_called = True

        def post_connect_cb(pipe):
            nonlocal post_connect_cb_was_called
            post_connect_cb_was_called = True

        s0.add_pre_pipe_connect_cb(pre_connect_cb)
        s0.add_post_pipe_connect_cb(post_connect_cb)
        s1.add_pre_pipe_connect_cb(pre_connect_cb)
        s1.add_post_pipe_connect_cb(post_connect_cb)

        s1.dial(addr)
        later = time.monotonic() + 5
        while later > time.monotonic():
            if pre_connect_cb_was_called:
                break
            # just give other threads a chance to run
            time.sleep(0.0001)
        assert pre_connect_cb_was_called
        wait_pipe_len(s0, 0)
        wait_pipe_len(s1, 0)
        assert not post_connect_cb_was_called


def test_post_pipe_connect_cb_works():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        post_called = False

        def post_connect_cb(pipe):
            nonlocal post_called
            post_called = True

        s0.add_post_pipe_connect_cb(post_connect_cb)
        s1.dial(addr)

        later = time.monotonic() + 10
        while later > time.monotonic():
            if post_called:
                break
            time.sleep(0.0005)
        assert post_called


def test_post_pipe_remove_cb_works():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        post_called = False

        def post_remove_cb(pipe):
            nonlocal post_called
            post_called = True

        s0.add_post_pipe_remove_cb(post_remove_cb)
        s1.dial(addr)
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        assert not post_called

    later = time.monotonic() + 10
    while later > time.monotonic():
        if post_called:
            break
        time.sleep(0.0005)
    assert post_called


def test_can_send_from_pipe():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s0, \
         pynng.Pair0(dial=addr, recv_timeout=FAST_TIMEOUT) as s1:
        wait_pipe_len(s0, 1)
        pipe = s0.pipes[0]
        # Actually send from the pipe object
        pipe.send(b"hello from pipe")
        assert s1.recv() == b"hello from pipe"
        # Also test send_msg from pipe
        msg = pynng.Message(b"msg from pipe")
        pipe.send_msg(msg)
        assert s1.recv() == b"msg from pipe"


@pytest.mark.trio
async def test_can_asend_from_pipe():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s0, \
         pynng.Pair0(dial=addr, recv_timeout=FAST_TIMEOUT) as s1:
        wait_pipe_len(s0, 1)
        pipe = s0.pipes[0]
        await pipe.asend(b"hello from pipe async")
        assert await s1.arecv() == b"hello from pipe async"
        msg = pynng.Message(b"msg from pipe async")
        await pipe.asend_msg(msg)
        assert await s1.arecv() == b"msg from pipe async"


def test_bad_callbacks_dont_cause_extra_failures():
    called_pre_connect = False

    def pre_connect_cb(pipe):
        nonlocal called_pre_connect
        called_pre_connect = True

    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0:
        # adding something that is not a callback should still allow correct
        # things to work.
        s0.add_pre_pipe_connect_cb(8)
        s0.add_pre_pipe_connect_cb(pre_connect_cb)
        with pynng.Pair0(dial=addr) as _:
            wait_pipe_len(s0, 1)
            later = time.monotonic() + 10
            while later > time.monotonic():
                if called_pre_connect:
                    break
                time.sleep(0.0005)
            assert called_pre_connect


def test_pipe_dialer_property():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, \
         pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s1, 1)
        pipe = s1.pipes[0]
        dialer = pipe.dialer
        assert dialer is s1.dialers[0]


def test_pipe_listener_property():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, \
         pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        pipe = s0.pipes[0]
        listener = pipe.listener
        assert listener is s0.listeners[0]


def test_pipe_dialer_raises_on_listener_side():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, \
         pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        pipe = s0.pipes[0]  # listener-side pipe
        with pytest.raises(TypeError):
            pipe.dialer


def test_pipe_listener_raises_on_dialer_side():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, \
         pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s1, 1)
        pipe = s1.pipes[0]  # dialer-side pipe
        with pytest.raises(TypeError):
            pipe.listener


def test_pipe_send_msg():
    addr = random_addr()
    with pynng.Pair1(listen=addr, polyamorous=True,
                      recv_timeout=FAST_TIMEOUT) as s0, \
         pynng.Pair1(dial=addr, polyamorous=True,
                      recv_timeout=FAST_TIMEOUT) as s1:
        wait_pipe_len(s0, 1)
        pipe = s0.pipes[0]
        msg = pynng.Message(b"pipe msg test")
        pipe.send_msg(msg)
        assert s1.recv() == b"pipe msg test"


def test_pipe_properties():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0, \
         pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        pipe = s0.pipes[0]
        assert pipe.protocol_name == "pair"


def test_pipes_access_under_contention():
    """Concurrent pipes access with connection churn does not crash."""
    addr = random_addr()
    listener = pynng.Pair0(listen=addr)
    errors = []

    def access_pipes():
        try:
            for _ in range(100):
                _ = listener.pipes
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=access_pipes) for _ in range(4)]
    for t in threads:
        t.start()

    dialers = []
    for _ in range(10):
        d = pynng.Pair0(dial=addr)
        dialers.append(d)

    for t in threads:
        t.join()

    for d in dialers:
        d.close()
    listener.close()

    assert not errors, f"Thread errors: {errors}"


def test_active_handles_registry():
    from pynng.nng import _active_handles, _active_handles_lock, lib
    addr = random_addr()
    s0 = pynng.Pair0(listen=addr)
    sock_id = lib.nng_socket_id(s0.socket)
    key = (s0._version_tag, sock_id)
    with _active_handles_lock:
        assert key in _active_handles
        assert _active_handles[key]() is s0

    s0.close()
    with _active_handles_lock:
        assert key not in _active_handles


def test_active_handles_reused_id_protection():
    import weakref
    from pynng.nng import _active_handles, _active_handles_lock, lib
    addr = random_addr()
    s0 = pynng.Pair0(listen=addr)
    sock_id = lib.nng_socket_id(s0.socket)
    key = (s0._version_tag, sock_id)

    # Simulate another socket reusing sock_id
    class Dummy:
        pass

    dummy = Dummy()
    dummy_ref = weakref.ref(dummy)
    with _active_handles_lock:
        _active_handles[key] = dummy_ref

    # Closing s0 should not remove the dummy_ref because s0 is not dummy
    s0.close()
    with _active_handles_lock:
        assert _active_handles.get(key) is dummy_ref
        del _active_handles[key]


def test_unclosed_socket_garbage_collected():
    import gc
    import weakref
    from pynng.nng import _active_handles, _active_handles_lock, lib
    addr = random_addr()
    s = pynng.Pair0(listen=addr)
    sock_id = lib.nng_socket_id(s.socket)
    vtag = getattr(s, "_version_tag", None)
    key = (vtag, sock_id) if vtag else sock_id
    with _active_handles_lock:
        assert key in _active_handles
    wr = weakref.ref(s)
    del s
    gc.collect()
    assert wr() is None, "Unclosed socket leaked and was not garbage-collected!"
    with _active_handles_lock:
        assert key not in _active_handles


def test_pipe_cb_does_not_deadlock_on_socket_operations():
    addr = random_addr()
    cb_called = False
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        def cb(pipe):
            nonlocal cb_called
            cb_called = True
            # Modifying callbacks or registering new ones from within callback
            # must not deadlock (verifies lock was released before callback invocation)
            s0.add_post_pipe_connect_cb(lambda p: None)

        s0.add_post_pipe_connect_cb(cb)
        s1.dial(addr)
        later = time.time() + 5.0
        while later > time.time():
            if cb_called:
                break
            time.sleep(0.001)
        assert cb_called


def test_socket_close_idempotent_multithreaded():
    import concurrent.futures
    addr = random_addr()
    s0 = pynng.Pair0(listen=addr)

    def close_sock():
        s0.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(close_sock) for _ in range(16)]
        for f in futures:
            f.result()

    assert s0._socket_closed


def test_pipe_callback_thread_safety():
    import concurrent.futures
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0:
        cbs = [lambda p: None for _ in range(20)]

        def add_rem(cb):
            s0.add_pre_pipe_connect_cb(cb)
            s0.add_post_pipe_connect_cb(cb)
            s0.add_post_pipe_remove_cb(cb)
            s0.remove_pre_pipe_connect_cb(cb)
            s0.remove_post_pipe_connect_cb(cb)
            s0.remove_post_pipe_remove_cb(cb)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(add_rem, cb) for cb in cbs]
            for f in futures:
                f.result()

        assert len(s0._on_pre_pipe_add) == 0
        assert len(s0._on_post_pipe_add) == 0
        assert len(s0._on_post_pipe_remove) == 0


def test_nng_pipe_cb_invalid_handle_safe(caplog):
    import logging
    from pynng.nng import _nng_pipe_cb, ffi, lib
    # Passing NULL or invalid pointer to _nng_pipe_cb should not raise or crash,
    # and should log an informational message that the event was ignored.
    with caplog.at_level(logging.INFO):
        _nng_pipe_cb(ffi.NULL, lib.NNG_PIPE_EV_ADD_PRE, ffi.NULL)
    assert any("invalid handle" in record.message for record in caplog.records)


def test_v2_nng_pipe_cb_invalid_handle_safe(caplog):
    import logging
    try:
        from pynng.v2._callbacks import _nng_pipe_cb
        from pynng._nng_v2 import ffi, lib
    except ImportError:
        pytest.skip("v2 extension not available")
    with caplog.at_level(logging.INFO):
        _nng_pipe_cb(ffi.NULL, lib.NNG_PIPE_EV_ADD_PRE, ffi.NULL)
    assert any("invalid handle" in record.message for record in caplog.records)


def _v1_pipe_cb():
    from pynng.nng import _nng_pipe_cb, ffi, lib

    return _nng_pipe_cb, ffi, lib


@contextlib.contextmanager
def _live_lib_pipe():
    """Yield the nng_pipe of a connected v1 pipe owned by another socket pair.

    Synthetic events for this pipe id then describe a pipe that nng still
    knows, as real ADD_PRE and ADD_POST events do.
    """
    addr = random_addr()
    with pynng.Pair0(listen=addr) as a, pynng.Pair0(dial=addr) as b:
        wait_pipe_len(a, 1)
        wait_pipe_len(b, 1)
        yield b.pipes[0].pipe


def test_post_pipe_remove_cb_waits_for_running_post_connect_cb():
    _nng_pipe_cb, _, lib = _v1_pipe_cb()
    events = []
    rem_threads = []
    removed = threading.Event()

    with _live_lib_pipe() as lib_pipe, pynng.Pair0() as s0:

        def post_add(p):
            events.append("post_add start")
            t = threading.Thread(
                target=_nng_pipe_cb,
                args=(lib_pipe, lib.NNG_PIPE_EV_REM_POST, s0._handle),
            )
            rem_threads.append(t)
            t.start()
            # Give a dispatcher that does not wait the chance to run post_remove.
            removed.wait(1.0)
            events.append("post_add end")

        def on_remove(p):
            events.append("remove")
            removed.set()

        s0.add_post_pipe_connect_cb(post_add)
        s0.add_post_pipe_remove_cb(on_remove)
        _nng_pipe_cb(lib_pipe, lib.NNG_PIPE_EV_ADD_PRE, s0._handle)
        _nng_pipe_cb(lib_pipe, lib.NNG_PIPE_EV_ADD_POST, s0._handle)
        rem_threads[0].join(5)
        assert not rem_threads[0].is_alive()
        assert events == ["post_add start", "post_add end", "remove"]
        assert s0.pipes == ()


def test_add_post_after_rem_post_is_dropped():
    _nng_pipe_cb, _, lib = _v1_pipe_cb()
    events = []
    with _live_lib_pipe() as lib_pipe, pynng.Pair0() as s0:
        pipe_id = lib.nng_pipe_id(lib_pipe)
        s0.add_pre_pipe_connect_cb(lambda p: events.append(("pre_add", p.id)))
        s0.add_post_pipe_connect_cb(lambda p: events.append(("post_add", p.id)))
        s0.add_post_pipe_remove_cb(lambda p: events.append(("remove", p.id)))

        _nng_pipe_cb(lib_pipe, lib.NNG_PIPE_EV_ADD_PRE, s0._handle)
        assert [p.id for p in s0.pipes] == [pipe_id]
        _nng_pipe_cb(lib_pipe, lib.NNG_PIPE_EV_REM_POST, s0._handle)
        assert s0.pipes == ()
        _nng_pipe_cb(lib_pipe, lib.NNG_PIPE_EV_ADD_POST, s0._handle)
        assert s0.pipes == ()
        assert events == [("pre_add", pipe_id), ("remove", pipe_id)]


def test_add_events_after_rem_post_for_unseen_pipe_are_dropped():
    _nng_pipe_cb, _, lib = _v1_pipe_cb()
    events = []
    with _live_lib_pipe() as lib_pipe, pynng.Pair0() as s0:
        s0.add_pre_pipe_connect_cb(lambda p: events.append("pre_add"))
        s0.add_post_pipe_connect_cb(lambda p: events.append("post_add"))
        s0.add_post_pipe_remove_cb(lambda p: events.append("remove"))

        _nng_pipe_cb(lib_pipe, lib.NNG_PIPE_EV_REM_POST, s0._handle)
        _nng_pipe_cb(lib_pipe, lib.NNG_PIPE_EV_ADD_PRE, s0._handle)
        _nng_pipe_cb(lib_pipe, lib.NNG_PIPE_EV_ADD_POST, s0._handle)

        assert s0.pipes == ()
        assert events == []


def test_pipe_callbacks_can_read_socket_pipes(nng):
    """Reading Socket.pipes during a pipe callback must not block on the
    socket's pipe lock."""
    addr = random_addr()
    results = []
    blocked = []
    done = threading.Event()

    def on_post_add(p):
        reader = threading.Thread(
            target=lambda: results.append([q.id for q in s0.pipes])
        )
        reader.start()
        reader.join(5)
        blocked.append(reader.is_alive())
        done.set()

    with nng.Pair0(listen=addr) as s0:
        s0.add_post_pipe_connect_cb(on_post_add)
        with nng.Pair0(dial=addr):
            assert done.wait(10)
            wait_pipe_len(s0, 1)
            assert blocked == [False]
            assert results == [[s0.pipes[0].id]]
