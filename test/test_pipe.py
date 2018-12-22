"""
Let's test up those pipes
"""


import time

import pynng


addr = 'tcp://127.0.0.1:31414'


def wait_pipe_len(sock, expected, timeout=5):
    """
    Wait up to ``timeout`` seconds for the length of sock.pipes to become
    ``expected`` value.  This prevents hardcoding sleep times, which should be
    pretty small for local development but potentially pretty large for CI
    runs.

    """
    now = time.time()
    later = now + timeout
    while time.time() < later and len(sock.pipes) != expected:
        time.sleep(0.001)
    return len(sock.pipes) == expected


def test_pipe_gets_added_and_removed():
    # add sleeps to ensure the nng_pipe_cb gets called.
    with pynng.Pair0(listen=addr, recv_timeout=1000) as s0, \
            pynng.Pair0(recv_timeout=1000) as s1:
        assert len(s0.pipes) == 0
        assert len(s1.pipes) == 0
        s1.dial(addr)
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)
    assert wait_pipe_len(s0, 0)
    assert wait_pipe_len(s1, 0)


def test_close_pipe_works():
    # add sleeps to ensure the nng_pipe_cb gets called.
    with pynng.Pair0(listen=addr, recv_timeout=1000) as s0, \
            pynng.Pair0(dial=addr, recv_timeout=1000) as s1:
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)
        pipe0 = s0.pipes[0]
        pipe1 = s1.pipes[0]
        assert pipe0.id != -1
        assert pipe1.id != -1
        pipe0.close()
        assert wait_pipe_len(s0, 0)
        assert wait_pipe_len(s1, 0)


def test_pipe_local_and_remote_addresses():
    with pynng.Pair0(listen=addr, recv_timeout=1000) as s0, \
            pynng.Pair0(dial=addr, recv_timeout=1000) as s1:
        assert wait_pipe_len(s0, 1)
        assert wait_pipe_len(s1, 1)
        p0 = s0.pipes[0]
        p1 = s1.pipes[0]
        local_address_0 = p0.local_address
        local_address_1 = p1.local_address
        assert str(local_address_0) == addr.replace('tcp://', '')
        assert str(local_address_1) != str(local_address_0)

