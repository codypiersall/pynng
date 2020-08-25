"""
Let's test up those pipes
"""


import time

import pytest

import pynng
from _test_util import wait_pipe_len

addr = 'inproc://test-addr'


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
    with pynng.Pair0(listen=addr) as s0, \
            pynng.Pair0(reconnect_time_min=40000, dial=addr) as s1:
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)
        pipe0 = s0.pipes[0]
        pipe0.close()
        assert wait_pipe_len(s0, 0)
        assert wait_pipe_len(s1, 0)


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
        s0.name = 's0'
        s1.name = 's1'
        pre_called = False
        post_connect_called = False
        post_remove_called = False

        def pre_connect_cb(pipe):
            pipe.close()
            nonlocal pre_called
            pre_called = True

        def post_connect_cb(pipe):
            nonlocal post_connect_called
            post_connect_called = True

        def post_remove_cb(pipe):
            nonlocal post_remove_called
            post_remove_called = True

        s0.add_pre_pipe_connect_cb(pre_connect_cb)
        s0.add_post_pipe_connect_cb(post_connect_cb)
        s1.dial(addr)
        later = time.time() + 5
        while later > time.time():
            if pre_called:
                break
        assert pre_called
        time.sleep(0.5)
        assert not post_connect_called
        assert not post_remove_called
        # TODO: These lines *should* work and yet they don't consistently work.
        # assert len(s0.pipes) == 0
        # assert len(s1.pipes) == 0


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


def test_can_send_from_pipe():
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        s0.send(b'hello')
        assert s1.recv() == b'hello'
        s0.send_msg(pynng.Message(b'it is me again'))
        assert s1.recv() == b'it is me again'
        time.sleep(0.05)


@pytest.mark.trio
async def test_can_asend_from_pipe():
    with pynng.Pair0(listen=addr) as s0, pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        await s0.asend(b'hello')
        assert await s1.arecv() == b'hello'
        await s0.asend_msg(pynng.Message(b'it is me again'))
        assert await s1.arecv() == b'it is me again'


def test_bad_callbacks_dont_cause_extra_failures():
    called_pre_connect = False

    def pre_connect_cb(pipe):
        nonlocal called_pre_connect
        called_pre_connect = True

    with pynng.Pair0(listen=addr) as s0:
        # adding something that is not a callback should still allow correct
        # things to work.
        s0.add_pre_pipe_connect_cb(8)
        s0.add_pre_pipe_connect_cb(pre_connect_cb)
        with pynng.Pair0(dial=addr) as _:
            wait_pipe_len(s0, 1)
            later = time.time() + 10
            while later > time.time():
                if called_pre_connect:
                    break
            assert called_pre_connect
