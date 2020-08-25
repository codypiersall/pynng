import pytest
import pynng
from _test_util import wait_pipe_len

addr = 'inproc://test-addr'

# timeout, ms
to = 1000


def test_socket_send_recv_msg_from_pipe():
    with pynng.Pair0(listen=addr, recv_timeout=to) as s1, \
            pynng.Pair0(dial=addr, recv_timeout=to) as s2:
        wait_pipe_len(s1, 1)
        pipe = s1.pipes[0]
        msg = pynng.Message(b'oh hello friend', pipe)
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
        msg = pynng.Message(b'we are friends, old buddy')
        s1.send_msg(msg)
        msg2 = s2.recv_msg()
        assert msg2.bytes == b'we are friends, old buddy'


@pytest.mark.trio
async def test_socket_arecv_asend_msg():
    with pynng.Pair0(listen=addr, recv_timeout=to) as s1, \
            pynng.Pair0(dial=addr, recv_timeout=to) as s2:
        wait_pipe_len(s1, 1)
        msg = pynng.Message(b'you truly are a pal')
        await s1.asend_msg(msg)
        msg2 = await s2.arecv_msg()
        assert msg2.bytes == b'you truly are a pal'
        assert msg2.pipe is s2.pipes[0]


@pytest.mark.trio
async def test_context_arecv_asend_msg():
    with pynng.Req0(listen=addr, recv_timeout=to) as s1, \
            pynng.Rep0(dial=addr, recv_timeout=to) as s2:
        with s1.new_context() as ctx1, s2.new_context() as ctx2:
            wait_pipe_len(s1, 1)
            msg = pynng.Message(b'do i even know you')
            await ctx1.asend_msg(msg)
            msg2 = await ctx2.arecv_msg()
            assert msg2.pipe is s2.pipes[0]
            assert msg2.bytes == b'do i even know you'
            msg3 = pynng.Message(b'yes of course i am your favorite platypus')
            await ctx2.asend_msg(msg3)
            msg4 = await ctx1.arecv_msg()
            assert msg4.pipe is s1.pipes[0]
            assert msg4.bytes == b'yes of course i am your favorite platypus'


def test_context_recv_send_msg():
    with pynng.Req0(listen=addr, recv_timeout=to) as s1, \
            pynng.Rep0(dial=addr, recv_timeout=to) as s2:
        with s1.new_context() as ctx1, s2.new_context() as ctx2:
            wait_pipe_len(s1, 1)
            msg = pynng.Message(b'do i even know you')
            ctx1.send_msg(msg)
            msg2 = ctx2.recv_msg()
            assert msg2.pipe is s2.pipes[0]
            assert msg2.bytes == b'do i even know you'
            msg3 = pynng.Message(b'yes of course i am your favorite platypus')
            ctx2.send_msg(msg3)
            msg4 = ctx1.recv_msg()
            assert msg4.pipe is s1.pipes[0]
            assert msg4.bytes == b'yes of course i am your favorite platypus'


def test_cannot_double_send():
    # double send would cause a SEGFAULT!!! That's no good
    with pynng.Req0(listen=addr, recv_timeout=to) as s1, \
            pynng.Rep0(dial=addr, recv_timeout=to) as s2:
        msg = pynng.Message(b'this is great')
        s1.send_msg(msg)
        with pytest.raises(pynng.MessageStateError):
            s1.send_msg(msg)

        with s1.new_context() as ctx:
            msg = pynng.Message(b'this also is great')
            ctx.send_msg(msg)
            with pytest.raises(pynng.MessageStateError):
                ctx.send_msg(msg)

        # don't really need to receive, but linters hate not using s2
        s2.recv_msg()


@pytest.mark.trio
async def test_cannot_double_asend():
    # double send would cause a SEGFAULT!!! That's no good
    with pynng.Req0(listen=addr, recv_timeout=to) as s1, \
            pynng.Rep0(dial=addr, recv_timeout=to) as s2:
        msg = pynng.Message(b'this is great')
        await s1.asend_msg(msg)
        with pytest.raises(pynng.MessageStateError):
            await s1.asend_msg(msg)

        with s1.new_context() as ctx:
            msg = pynng.Message(b'this also is great')
            await ctx.asend_msg(msg)
            with pytest.raises(pynng.MessageStateError):
                await ctx.asend_msg(msg)

        # don't really need to receive, but linters hate not using s2
        await s2.arecv_msg()
