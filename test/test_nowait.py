import time
import pytest
import pynng


def poll_nowait(fn, timeout=1.0):
    """Poll a non-blocking nowait function until it succeeds or times out."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return fn()
        except pynng.TryAgain:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.001)


def test_socket_recv_nowait_empty_raises_tryagain():
    """Verify recv_nowait raises TryAgain when socket is empty."""
    with pynng.Pair0(listen="inproc://test-nowait-1") as s1:
        with pytest.raises(pynng.TryAgain):
            s1.recv_nowait()
        with pytest.raises(pynng.TryAgain):
            s1.recv_msg_nowait()

        buf = bytearray(16)
        with pytest.raises(pynng.TryAgain):
            s1.recv_into_nowait(buf)


def test_socket_send_recv_nowait():
    """Verify send_nowait and recv_nowait roundtrip."""
    addr = "inproc://test-nowait-2"
    with pynng.Pair0(listen=addr) as s1, pynng.Pair0(dial=addr) as s2:
        poll_nowait(lambda: s1.send_nowait(b"hello nowait"))
        data = poll_nowait(s2.recv_nowait)
        assert data == b"hello nowait"

        poll_nowait(lambda: s2.send_nowait(b"hello back"))
        data2 = poll_nowait(s1.recv_nowait)
        assert data2 == b"hello back"


def test_socket_send_recv_msg_nowait():
    """Verify send_msg_nowait and recv_msg_nowait roundtrip."""
    addr = "inproc://test-nowait-3"
    with pynng.Pair0(listen=addr) as s1, pynng.Pair0(dial=addr) as s2:
        msg = pynng.Message(b"msg nowait")
        poll_nowait(lambda: s1.send_msg_nowait(msg))
        recvd = poll_nowait(s2.recv_msg_nowait)
        assert recvd.bytes == b"msg nowait"

        msg2 = pynng.Message(b"msg back")
        poll_nowait(lambda: s2.send_msg_nowait(msg2))
        recvd2 = poll_nowait(s1.recv_msg_nowait)
        assert recvd2.bytes == b"msg back"


def test_socket_recv_into_nowait():
    """Verify recv_into_nowait writes into buffer."""
    addr = "inproc://test-nowait-4"
    with pynng.Pair0(listen=addr) as s1, pynng.Pair0(dial=addr) as s2:
        poll_nowait(lambda: s1.send_nowait(b"into payload"))
        buf = bytearray(32)
        nbytes = poll_nowait(lambda: s2.recv_into_nowait(buf))
        assert nbytes == len(b"into payload")
        assert bytes(buf[:nbytes]) == b"into payload"

        poll_nowait(lambda: s2.send_nowait(b"into return payload"))
        buf2 = bytearray(32)
        nbytes2 = poll_nowait(lambda: s1.recv_into_nowait(buf2))
        assert nbytes2 == len(b"into return payload")
        assert bytes(buf2[:nbytes2]) == b"into return payload"


def test_context_recv_nowait_empty_raises_tryagain():
    """Verify Context nowait methods raise TryAgain when empty."""
    addr = "inproc://test-nowait-ctx-1"
    with pynng.Rep0(listen=addr) as s1:
        ctx = s1.new_context()
        with pytest.raises(pynng.TryAgain):
            ctx.recv_nowait()
        with pytest.raises(pynng.TryAgain):
            ctx.recv_msg_nowait()

        buf = bytearray(16)
        with pytest.raises(pynng.TryAgain):
            ctx.recv_into_nowait(buf)


def test_context_send_recv_nowait():
    """Verify Context nowait methods roundtrip."""
    addr = "inproc://test-nowait-ctx-2"
    with pynng.Rep0(listen=addr) as rep, pynng.Req0(dial=addr) as req:
        ctx_req = req.new_context()
        ctx_rep = rep.new_context()

        poll_nowait(lambda: ctx_req.send_nowait(b"request data"))
        req_msg = poll_nowait(ctx_rep.recv_msg_nowait)
        assert req_msg.bytes == b"request data"

        resp_msg = pynng.Message(b"response data")
        poll_nowait(lambda: ctx_rep.send_msg_nowait(resp_msg))
        resp = poll_nowait(ctx_req.recv_nowait)
        assert resp == b"response data"

        # Round 2
        poll_nowait(lambda: ctx_req.send_nowait(b"request 2"))
        buf = bytearray(32)
        nbytes = poll_nowait(lambda: ctx_rep.recv_into_nowait(buf))
        assert bytes(buf[:nbytes]) == b"request 2"

        poll_nowait(lambda: ctx_rep.send_msg_nowait(pynng.Message(b"response 2")))
        recvd_resp = poll_nowait(ctx_req.recv_msg_nowait)
        assert recvd_resp.bytes == b"response 2"


def test_v2_socket_nowait():
    """Verify pynng.v2 sockets also inherit nowait methods."""
    from pynng import v2

    addr = "inproc://test-nowait-v2"
    with v2.Pair0(listen=addr) as s1, v2.Pair0(dial=addr) as s2:
        with pytest.raises(pynng.TryAgain):
            s1.recv_nowait()

        poll_nowait(lambda: s1.send_nowait(b"v2 payload"))
        assert poll_nowait(s2.recv_nowait) == b"v2 payload"
