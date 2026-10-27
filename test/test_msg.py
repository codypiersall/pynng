import contextlib
import io
import time

import pytest
import pynng
from _test_util import wait_pipe_len
from conftest import random_addr, FAST_TIMEOUT


def test_socket_send_recv_msg_from_pipe():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        wait_pipe_len(s1, 1)
        pipe = s1.pipes[0]
        msg = pynng.Message(b"oh hello friend", pipe)
        assert isinstance(msg, pynng.Message)
        assert msg.bytes == b"oh hello friend"
        s1.send_msg(msg)
        assert msg.pipe is pipe
        msg2 = s2.recv_msg()
        assert isinstance(msg2, pynng.Message)
        assert msg2.bytes == b"oh hello friend"
        assert msg2.pipe is s2.pipes[0]


def test_socket_send_recv_msg():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        wait_pipe_len(s1, 1)
        msg = pynng.Message(b"we are friends, old buddy")
        s1.send_msg(msg)
        msg2 = s2.recv_msg()
        assert msg2.bytes == b"we are friends, old buddy"
        # Verify pipe was associated on receive
        assert msg2.pipe is not None
        assert msg2.pipe is s2.pipes[0]


@pytest.mark.trio
async def test_socket_arecv_asend_msg():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        wait_pipe_len(s1, 1)
        msg = pynng.Message(b"you truly are a pal")
        await s1.asend_msg(msg)
        msg2 = await s2.arecv_msg()
        assert msg2.bytes == b"you truly are a pal"
        assert msg2.pipe is s2.pipes[0]


@pytest.mark.trio
async def test_context_arecv_asend_msg():
    addr = random_addr()
    with pynng.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Rep0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        with s1.new_context() as ctx1, s2.new_context() as ctx2:
            wait_pipe_len(s1, 1)
            msg = pynng.Message(b"do i even know you")
            await ctx1.asend_msg(msg)
            msg2 = await ctx2.arecv_msg()
            assert msg2.pipe is s2.pipes[0]
            assert msg2.bytes == b"do i even know you"
            msg3 = pynng.Message(b"yes of course i am your favorite platypus")
            await ctx2.asend_msg(msg3)
            msg4 = await ctx1.arecv_msg()
            assert msg4.pipe is s1.pipes[0]
            assert msg4.bytes == b"yes of course i am your favorite platypus"


def test_context_recv_send_msg():
    addr = random_addr()
    with pynng.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Rep0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        with s1.new_context() as ctx1, s2.new_context() as ctx2:
            wait_pipe_len(s1, 1)
            msg = pynng.Message(b"do i even know you")
            ctx1.send_msg(msg)
            msg2 = ctx2.recv_msg()
            assert msg2.pipe is s2.pipes[0]
            assert msg2.bytes == b"do i even know you"
            msg3 = pynng.Message(b"yes of course i am your favorite platypus")
            ctx2.send_msg(msg3)
            msg4 = ctx1.recv_msg()
            assert msg4.pipe is s1.pipes[0]
            assert msg4.bytes == b"yes of course i am your favorite platypus"


def test_cannot_double_send():
    # double send would cause a SEGFAULT!!! That's no good
    addr = random_addr()
    with pynng.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Rep0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        msg = pynng.Message(b"this is great")
        s1.send_msg(msg)
        with pytest.raises(pynng.MessageStateError):
            s1.send_msg(msg)

        with s1.new_context() as ctx:
            msg = pynng.Message(b"this also is great")
            ctx.send_msg(msg)
            with pytest.raises(pynng.MessageStateError):
                ctx.send_msg(msg)

        # don't really need to receive, but linters hate not using s2
        s2.recv_msg()


@pytest.mark.trio
async def test_cannot_double_asend():
    # double send would cause a SEGFAULT!!! That's no good
    addr = random_addr()
    with pynng.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Rep0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        msg = pynng.Message(b"this is great")
        await s1.asend_msg(msg)
        with pytest.raises(pynng.MessageStateError):
            await s1.asend_msg(msg)

        with s1.new_context() as ctx:
            msg = pynng.Message(b"this also is great")
            await ctx.asend_msg(msg)
            with pytest.raises(pynng.MessageStateError):
                await ctx.asend_msg(msg)

        # don't really need to receive, but linters hate not using s2
        await s2.arecv_msg()


def test_message_del_without_send():
    import gc
    msg = pynng.Message(b"never sent")
    del msg
    stderr_capture = io.StringIO()
    with contextlib.redirect_stderr(stderr_capture):
        gc.collect()
    stderr_output = stderr_capture.getvalue()
    assert stderr_output == "", f"__del__ raised during gc: {stderr_output!r}"


def test_message_del_after_send():
    import gc
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, \
         pynng.Pair0(dial=addr, recv_timeout=FAST_TIMEOUT) as s2:
        wait_pipe_len(s1, 1)
        msg = pynng.Message(b"test data")
        s1.send_msg(msg)
        assert s2.recv() == b"test data"
        del msg
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            gc.collect()
        stderr_output = stderr_capture.getvalue()
        assert stderr_output == "", f"__del__ raised during gc: {stderr_output!r}"


def test_message_pipe_setter_rejects_non_pipe():
    msg = pynng.Message(b"test")
    with pytest.raises(ValueError):
        msg.pipe = "not a pipe"
    with pytest.raises(ValueError):
        msg.pipe = 42


def test_message_mem_freed_after_send():
    """Verify that sending a message marks it as freed so __del__ doesn't double-free"""
    addr = random_addr()
    with pynng.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Rep0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        wait_pipe_len(s1, 1)
        msg = pynng.Message(b"test data")
        assert not msg._mem_freed
        s1.send_msg(msg)
        assert msg._mem_freed
        # __del__ should not crash since _mem_freed is True
        msg.__del__()
        s2.recv_msg()


def test_buffer_after_send_raises():
    """Accessing _buffer after send raises MessageStateError."""
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as sender, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as receiver:
        wait_pipe_len(sender, 1)
        msg = pynng.Message(b"hello")
        sender.send_msg(msg)
        with pytest.raises(pynng.MessageStateError):
            _ = msg._buffer
        received = receiver.recv()
        assert received == b"hello"


def test_recv_zero_byte_pair0():
    """Verify receiving 0-byte messages via v1 Socket.recv() on Pair0 (Issue #104)."""
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        wait_pipe_len(s1, 1)
        wait_pipe_len(s2, 1)

        # Blocking recv of 0-byte message
        s1.send(b"")
        recvd = s2.recv()
        assert recvd == b""
        assert len(recvd) == 0

        # Non-blocking recv of 0-byte message
        s1.send(b"")
        for _ in range(50):
            try:
                recvd_nb = s2.recv(block=False)
                break
            except pynng.TryAgain:
                time.sleep(0.01)
        else:
            pytest.fail("Did not receive 0-byte message with block=False")
        assert recvd_nb == b""
        assert len(recvd_nb) == 0


def test_recv_zero_byte_reqrep0():
    """Verify receiving 0-byte messages via v1 Socket.recv() on Req0/Rep0 (Issue #104)."""
    addr = random_addr()
    with pynng.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as req, pynng.Rep0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as rep:
        wait_pipe_len(req, 1)
        wait_pipe_len(rep, 1)

        # req sends 0-byte request, rep receives (blocking)
        req.send(b"")
        recvd = rep.recv()
        assert recvd == b""
        assert len(recvd) == 0

        # rep sends 0-byte response, req receives (blocking)
        rep.send(b"")
        recvd = req.recv()
        assert recvd == b""
        assert len(recvd) == 0

        # Test non-blocking recv with 0-byte request and response
        req.send(b"")
        for _ in range(50):
            try:
                recvd_nb = rep.recv(block=False)
                break
            except pynng.TryAgain:
                time.sleep(0.01)
        else:
            pytest.fail("Rep did not receive 0-byte message with block=False")
        assert recvd_nb == b""
        assert len(recvd_nb) == 0

        rep.send(b"")
        for _ in range(50):
            try:
                recvd_nb = req.recv(block=False)
                break
            except pynng.TryAgain:
                time.sleep(0.01)
        else:
            pytest.fail("Req did not receive 0-byte message with block=False")
        assert recvd_nb == b""
        assert len(recvd_nb) == 0


def test_recv_zero_byte_pushpull0():
    """Verify receiving 0-byte messages via v1 Socket.recv() on Push0/Pull0 (Issue #104)."""
    addr = random_addr()
    with pynng.Push0(listen=addr) as push, pynng.Pull0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as pull:
        wait_pipe_len(push, 1)
        wait_pipe_len(pull, 1)

        # Blocking recv of 0-byte message
        push.send(b"")
        recvd = pull.recv()
        assert recvd == b""
        assert len(recvd) == 0

        # Non-blocking recv of 0-byte message
        push.send(b"")
        for _ in range(50):
            try:
                recvd_nb = pull.recv(block=False)
                break
            except pynng.TryAgain:
                time.sleep(0.01)
        else:
            pytest.fail("Pull did not receive 0-byte message with block=False")
        assert recvd_nb == b""
        assert len(recvd_nb) == 0


class _InterruptAfterCall:
    """cffi lib proxy that raises KeyboardInterrupt when its n-th function call
    returns.

    This is what CPython does when SIGINT arrives during a blocking C call: the
    call completes, and the interrupt is raised before its result is stored.
    """

    def __init__(self, lib, n):
        self._real_lib = lib
        self._n = n
        self.calls = 0

    def __getattr__(self, name):
        attr = getattr(self._real_lib, name)
        if not callable(attr):
            return attr

        def call(*args):
            result = attr(*args)
            self.calls += 1
            if self.calls == self._n:
                raise KeyboardInterrupt
            return result

        return call


def _send_interrupted_after_each_call(sock, send, receiver):
    """Send one message per lib call of ``send``, interrupting after that call.

    Returns ``(consumed, mem_freed, intact)`` for each interruption point, where
    ``consumed`` means the receiver got the message.
    """
    real_lib = sock._lib
    outcomes = []
    n = 1
    while True:
        payload = b"payload-%d" % n
        msg = pynng.Message(payload)
        sock._lib = _InterruptAfterCall(real_lib, n)
        try:
            send(msg)
        except KeyboardInterrupt:
            pass
        else:
            assert receiver.recv() == payload
            assert msg._mem_freed is True
            return outcomes
        finally:
            del sock._lib
        try:
            consumed = receiver.recv() == payload
        except pynng.Timeout:
            consumed = False
        intact = not consumed and not msg._mem_freed and msg.bytes == payload
        outcomes.append((consumed, msg._mem_freed, intact))
        if consumed:
            # Keep a failing run from freeing the msg a second time.
            msg._mem_freed = True
        n += 1


def test_socket_send_msg_interrupted_never_leaves_message_owning_sent_msg():
    addr = random_addr()
    with (
        pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s0,
        pynng.Pair0(dial=addr) as s1,
    ):
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        outcomes = _send_interrupted_after_each_call(s1, s1.send_msg, s0)
    # nng_sendmsg is the only lib call; nng owns the msg once it returns.
    assert outcomes == [(True, True, False)]


def test_context_send_msg_interrupted_never_leaves_message_owning_sent_msg():
    addr = random_addr()
    with (
        pynng.Rep0(listen=addr, recv_timeout=FAST_TIMEOUT) as rep,
        pynng.Req0(dial=addr) as req,
    ):
        wait_pipe_len(rep, 1)
        wait_pipe_len(req, 1)

        def send(msg):
            with req.new_context() as ctx:
                ctx.send_msg(msg)

        outcomes = _send_interrupted_after_each_call(req, send, rep)
    assert outcomes
    for consumed, mem_freed, intact in outcomes:
        # A Message that still owns a msg nng consumed would free it twice.
        assert (consumed, mem_freed, intact) in (
            (True, True, False),
            (False, False, True),
        )
