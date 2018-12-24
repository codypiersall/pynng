"""
Let's test up those pipes
"""


import sys
import time

import pynng


addr = 'tcp://127.0.0.1:31414'


def wait_pipe_len(sock, expected, timeout=10):
    """
    Wait up to ``timeout`` seconds for the length of sock.pipes to become
    ``expected`` value.  This prevents hardcoding sleep times, which should be
    pretty small for local development but potentially pretty large for CI
    runs.

    """
    now = time.time()
    later = now + timeout
    while time.time() < later and len(sock.pipes) != expected:
        time.sleep(0.002)
    return len(sock.pipes) == expected


def test_pipe_gets_added_and_removed():
    # add sleeps to ensure the nng_pipe_cb gets called.
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        assert len(s0.pipes) == 0
        assert len(s1.pipes) == 0
        s1.dial(addr)
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)
    assert wait_pipe_len(s0, 0)
    assert wait_pipe_len(s1, 0)


def test_close_pipe_works():
    # this is some racy business
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0(dial=addr) as s1:
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)
        pipe0 = s0.pipes[0]
        pipe0.close()
        # this is some racy business
        # s1 automatically re-dials whenever pipe0 closes. Hah!  So we better
        # call wait_pipe_len QUICKLY here.
        #
        # Probably we should just set reconnect_min_time to a big number, but
        # this is more exciting, and might even cause CI to fail.  Awesome!
        assert wait_pipe_len(s0, 0)
        assert wait_pipe_len(s1, 0)
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)


def test_pipe_local_and_remote_addresses():
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0(dial=addr) as s1:
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)
        p0 = s0.pipes[0]
        p1 = s1.pipes[0]
        local_addr0 = p0.local_address
        remote_addr0 = p0.remote_address
        local_addr1 = p1.local_address
        remote_addr1 = p1.remote_address
        assert str(local_addr0) == addr.replace('tcp://', '')
        assert str(local_addr0) == str(remote_addr1)
        # on Windows, the local address is 0.0.0.0:0
        if sys.platform == 'win32':
            assert str(local_addr1) == '0.0.0.0:0'
        else:
            assert str(local_addr1) == str(remote_addr0)


def test_pre_pipe_connect_cb_totally_works():
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        called = False

        def pre_connect_cb(_):
            nonlocal called
            called = True
        s0.add_pre_pipe_connect_cb(pre_connect_cb)
        s1.dial(addr)
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)
        assert called


def test_closing_pipe_in_pre_connect_works():
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        pre_called = False
        post_called = False

        def pre_connect_cb(pipe):
            pipe.close()
            nonlocal pre_called
            pre_called = True

        def post_connect_cb(pipe):
            pipe.close()
            nonlocal post_called
            post_called = True

        s0.add_pre_pipe_connect_cb(pre_connect_cb)
        s0.add_post_pipe_connect_cb(post_connect_cb)
        s1.dial(addr)
        later = time.time() + 5
        while later > time.time():
            if pre_called:
                break
        assert pre_called
        time.sleep(0.05)
        assert not post_called
        assert len(s0.pipes) == 0
        assert len(s1.pipes) == 0


def test_post_pipe_connect_cb_works():
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0() as s1:
        post_called = False

        def post_connect_cb(pipe):
            nonlocal post_called
            post_called = True

        s0.add_post_pipe_connect_cb(post_connect_cb)
        s1.dial(addr)

        later = time.time() + 10
        while later > time.time():
            if post_called:
                break
        assert post_called


def test_post_pipe_remove_cb_works():
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

    later = time.time() + 10
    while later > time.time():
        if post_called:
            break
    assert post_called

