"""
Let's test up those pipes
"""


import time

import pynng


addr = 'tcp://127.0.0.1:31414'


def test_pipe_gets_added_and_removed():
    # add sleeps to ensure the nng_pipe_cb gets called.
    with pynng.Pair0(listen=addr, recv_timeout=1000) as s0, \
            pynng.Pair0(recv_timeout=1000) as s1:
        assert len(s0.pipes) == 0
        assert len(s1.pipes) == 0
        s1.dial(addr)
        time.sleep(0.05)
        assert len(s0.pipes) == 1
        assert len(s1.pipes) == 1
    time.sleep(0.05)
    assert len(s0.pipes) == 0
    assert len(s1.pipes) == 0


def test_close_pipe_works():
    # add sleeps to ensure the nng_pipe_cb gets called.
    with pynng.Pair0(listen=addr, recv_timeout=1000) as s0, \
            pynng.Pair0(dial=addr, recv_timeout=1000) as s1:
        time.sleep(0.01)
        assert len(s0.pipes) == 1
        assert len(s1.pipes) == 1
        pipe0 = s0.pipes[0]
        pipe1 = s1.pipes[0]
        assert pipe1 is not pipe0
        assert pipe0.id != pipe1.id
        assert pipe0.socket is not pipe1.socket
        pipe0.close()
        time.sleep(0.05)
        assert len(s0.pipes) == 0
        assert len(s1.pipes) == 0

