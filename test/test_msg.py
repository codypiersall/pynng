from trio.testing import trio_test

import pynng
from test._test_util import wait_pipe_len

addr = 'tcp://127.0.0.1:42421'

# timeout, ms
to = 1000


def test_socket_send_recv_msg_from_pipe():
    with pynng.Pair0(listen=addr, recv_timeout=to) as s1, \
            pynng.Pair0(dial=addr, recv_timeout=to) as s2:
        wait_pipe_len(s1, 1)
        pipe = s1.pipes[0]
        msg = pipe.new_msg(b'oh hello friend')
        assert isinstance(msg, pynng.Message)
        assert msg.bytes == b'oh hello friend'
        s1.send_msg(msg)
        assert msg.pipe is pipe
        msg2 = s2.recv_msg()
        assert isinstance(msg2, pynng.Message)
        assert msg2.bytes == b'oh hello friend'
        assert msg2.pipe is s2.pipes[0]


def test_socket_send_recv_msg():
    with pynng.Pair0(listen=addr, recv_timeout=to) as s1, \
            pynng.Pair0(dial=addr, recv_timeout=to) as s2:
        wait_pipe_len(s1, 1)
        msg = s1.new_msg(b'we are friends, old buddy')
        s1.send_msg(msg)
        msg2 = s2.recv_msg()
        assert msg2.bytes == b'we are friends, old buddy'


@trio_test
async def test_arecv_asend_msg():
    with pynng.Pair0(listen=addr, recv_timeout=to) as s1, \
            pynng.Pair0(dial=addr, recv_timeout=to) as s2:
        wait_pipe_len(s1, 1)
        pipe = s1.pipes[0]
        msg = pipe.new_msg(b'you truly are a pal')
        await s1.asend_msg(msg)
        msg2 = await s2.arecv_msg()
        assert msg2.bytes == b'you truly are a pal'
        assert msg2.pipe is s2.pipes[0]
