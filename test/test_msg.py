import pynng
from test._test_util import wait_pipe_len

addr = 'tcp://127.0.0.1:42421'

# timeout, ms
to = 1000


def test_socket_send_recv_msg():
    with pynng.Pair0(listen=addr, recv_timeout=to) as s1, \
            pynng.Pair0(dial=addr, recv_timeout=to) as s2:
        wait_pipe_len(s1, 1)
        pipe = s1.pipes[0]
        msg = pipe.new_msg(b'oh hello friend')
        assert isinstance(msg, pynng.Message)
        assert msg.bytes == b'oh hello friend'
        msg.send()
        msg2 = s2.recv_msg()
        assert isinstance(msg2, pynng.Message)
        assert msg2.bytes == b'oh hello friend'


def test_recv_msg_has_correct_pipe():
    with pynng.Pair0(listen=addr, recv_timeout=to) as s1, \
            pynng.Pair0(dial=addr, recv_timeout=to) as s2:
        wait_pipe_len(s1, 1)
        pipe = s1.pipes[0]
        msg = pipe.new_msg(b'oh hello friend')
        assert msg.pipe is pipe
        msg.send()
        msg2 = s2.recv_msg()
        assert msg2.pipe is s2.pipes[0]
