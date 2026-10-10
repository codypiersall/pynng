"""End-to-end communication tests for all 11 NNG v2 socket types."""

import gc
import threading
import time
import pytest

import pynng
from _test_util import wait_pipe_len
from conftest import random_addr, FAST_TIMEOUT, MEDIUM_TIMEOUT

pytestmark = [pytest.mark.nng_v2]

# Ensure pynng.v2 is available before running these tests
v2 = pytest.importorskip("pynng.v2")


def test_v2_pair0():
    """Verify Pair0 bidirectional communication in v2."""
    addr = random_addr()
    with v2.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s0, v2.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s1:
        s1.send(b"hello from s1")
        assert s0.recv() == b"hello from s1"
        s0.send(b"reply from s0")
        assert s1.recv() == b"reply from s0"


def test_v2_pair0_dial_listen_instances():
    """Verify s.dial() and s.listen() return v2 Dialer/Listener subclasses."""
    addr = random_addr()
    with v2.Pair0() as s0, v2.Pair0() as s1:
        listener = s0.listen(addr)
        dialer = s1.dial(addr)
        assert isinstance(listener, v2.Listener)
        assert isinstance(dialer, v2.Dialer)


@pytest.mark.asyncio
async def test_v2_pair0_async():
    """Verify Pair0 async arecv/asend in v2."""
    addr = random_addr()
    with v2.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s0, v2.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s1:
        await s1.asend(b"async hello")
        assert await s0.arecv() == b"async hello"


def test_v2_pair1():
    """Verify Pair1 monogamous communication in v2."""
    addr = random_addr()
    with v2.Pair1(listen=addr, recv_timeout=FAST_TIMEOUT) as s0, v2.Pair1(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s1:
        s1.send(b"pair1 message")
        assert s0.recv() == b"pair1 message"


def test_v2_pair1_polyamorous():
    """Verify Pair1 polyamorous mode with multiple peers in v2."""
    addr = random_addr()
    with v2.Pair1(
        listen=addr, polyamorous=True, recv_timeout=FAST_TIMEOUT
    ) as s0, v2.Pair1(dial=addr, polyamorous=True, recv_timeout=FAST_TIMEOUT) as s1:
        assert s0.polyamorous is True
        assert s1.polyamorous is True
        wait_pipe_len(s0, 1)
        p1 = s0.pipes[0]

        with v2.Pair1(dial=addr, polyamorous=True, recv_timeout=FAST_TIMEOUT) as s2:
            assert s2.polyamorous is True
            wait_pipe_len(s0, 2)
            pipes = s0.pipes
            p2 = pipes[1] if pipes[0] is p1 else pipes[0]

            p1.send(b"msg to s1")
            assert s1.recv() == b"msg to s1"

            p2.send(b"msg to s2")
            assert s2.recv() == b"msg to s2"


def test_v2_req0_rep0():
    """Verify Req0 and Rep0 request-reply lifecycle and state machine in v2."""
    addr = random_addr()
    with v2.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as req, v2.Rep0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as rep:
        req.send(b"ping")
        assert rep.recv() == b"ping"
        rep.send(b"pong")
        assert req.recv() == b"pong"

        # Req cannot receive before sending
        with pytest.raises(pynng.BadState):
            req.recv()

        # Rep cannot send before receiving
        with pytest.raises(pynng.BadState):
            rep.send(b"unsolicited")


def test_v2_pub0_sub0():
    """Verify Pub0 and Sub0 topic matching in v2."""
    addr = random_addr()
    with v2.Sub0(listen=addr, recv_timeout=FAST_TIMEOUT) as sub, v2.Pub0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as pub:
        sub.subscribe(b"sports:")
        wait_pipe_len(sub, 1)
        wait_pipe_len(pub, 1)

        # Non-matching message is not received
        pub.send(b"weather: rainy")
        with pytest.raises(pynng.Timeout):
            sub.recv()

        # Matching message is received
        pub.send(b"sports: goals scored")
        assert sub.recv() == b"sports: goals scored"

        # Pub cannot recv
        with pytest.raises(pynng.NotSupported):
            pub.recv()

        # Sub cannot send
        with pytest.raises(pynng.NotSupported):
            sub.send(b"cannot send")


def test_v2_sub0_subscriptions_parity():
    """Verify Sub0 subscriptions property tracking parity in v2."""
    with v2.Sub0() as sub:
        assert sub.subscriptions == frozenset()

        sub.subscribe("news:")
        assert sub.subscriptions == frozenset({b"news:"})

        sub.subscribe(b"alerts:")
        assert sub.subscriptions == frozenset({b"news:", b"alerts:"})

        # Duplicates ignored in set
        sub.subscribe("news:")
        assert sub.subscriptions == frozenset({b"news:", b"alerts:"})

        sub.unsubscribe("news:")
        assert sub.subscriptions == frozenset({b"alerts:"})

        sub.subscribe_all(["cat1", b"cat2"])
        assert sub.subscriptions == frozenset({b"alerts:", b"cat1", b"cat2"})

        sub.unsubscribe_all()
        assert sub.subscriptions == frozenset()


def test_v2_sub0_constructor_topics():
    """Verify Sub0 constructor topic subscription in v2."""
    addr = random_addr()
    with v2.Pub0(listen=addr) as pub:
        with v2.Sub0(dial=addr, topics=["alpha", "beta"], recv_timeout=FAST_TIMEOUT) as sub:
            assert sub.subscriptions == frozenset({b"alpha", b"beta"})
            wait_pipe_len(sub, 1)
            wait_pipe_len(pub, 1)
            pub.send(b"alpha 1")
            assert sub.recv() == b"alpha 1"
            pub.send(b"beta 2")
            assert sub.recv() == b"beta 2"


def test_v2_push0_pull0():
    """Verify Push0 and Pull0 distribution in v2."""
    addr = random_addr()
    received = {"pull1": None, "pull2": None}
    with v2.Push0(listen=addr) as push, v2.Pull0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as pull1, v2.Pull0(dial=addr, recv_timeout=FAST_TIMEOUT) as pull2:

        def recv1():
            received["pull1"] = pull1.recv()

        def recv2():
            received["pull2"] = pull2.recv()

        t1 = threading.Thread(target=recv1, daemon=True)
        t2 = threading.Thread(target=recv2, daemon=True)

        t1.start()
        t2.start()
        wait_pipe_len(push, 2)
        wait_pipe_len(pull1, 1)
        wait_pipe_len(pull2, 1)

        push.send(b"item 1")
        push.send(b"item 2")
        t1.join()
        t2.join()

        assert {received["pull1"], received["pull2"]} == {b"item 1", b"item 2"}

        with pytest.raises(pynng.NotSupported):
            push.recv()


def test_v2_surveyor0_respondent0():
    """Verify Surveyor0 and Respondent0 survey lifecycle in v2."""
    addr = random_addr()
    with v2.Surveyor0(listen=addr, recv_timeout=MEDIUM_TIMEOUT) as surveyor, v2.Respondent0(
        dial=addr, recv_timeout=MEDIUM_TIMEOUT
    ) as resp1, v2.Respondent0(dial=addr, recv_timeout=MEDIUM_TIMEOUT) as resp2:
        wait_pipe_len(surveyor, 2)
        surveyor.send(b"survey question")

        assert resp1.recv() == b"survey question"
        resp1.send(b"resp1 answer")

        assert resp2.recv() == b"survey question"
        resp2.send(b"resp2 answer")

        answers = {surveyor.recv(), surveyor.recv()}
        assert answers == {b"resp1 answer", b"resp2 answer"}


def test_v2_bus0():
    """Verify Bus0 mesh broadcast in v2."""
    addr = random_addr()
    with v2.Bus0(recv_timeout=FAST_TIMEOUT) as s0, v2.Bus0(
        recv_timeout=FAST_TIMEOUT
    ) as s1, v2.Bus0(recv_timeout=FAST_TIMEOUT) as s2:
        s0.listen(addr)
        s1.dial(addr)
        s2.dial(addr)
        wait_pipe_len(s0, 2)

        s0.send(b"s1 and s2 get this")
        assert s1.recv() == b"s1 and s2 get this"
        assert s2.recv() == b"s1 and s2 get this"

        s1.send(b"only s0 gets this")
        assert s0.recv() == b"only s0 gets this"
        with pytest.raises(pynng.Timeout):
            s2.recv()


def test_v2_pipe_addresses():
    """Verify local_address and remote_address symmetry on v2 pipes."""
    addr = random_addr()
    with v2.Pair0(listen=addr) as s0, v2.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        p0 = s0.pipes[0]
        p1 = s1.pipes[0]

        assert isinstance(p0.local_address, pynng.sockaddr.InprocAddr)
        assert isinstance(p0.remote_address, pynng.sockaddr.InprocAddr)
        assert isinstance(p1.local_address, pynng.sockaddr.InprocAddr)
        assert isinstance(p1.remote_address, pynng.sockaddr.InprocAddr)

        # Symmetry: s0's local is s1's remote, and vice versa
        assert str(p0.local_address) == str(p1.remote_address)
        assert str(p0.remote_address) == str(p1.local_address)


def test_v2_dialer_listener_addresses_graceful():
    """Verify dialer and listener local/remote address access does not raise."""
    addr = random_addr()
    with v2.Pair0() as s0, v2.Pair0() as s1:
        l = s0.listen(addr)
        d = s1.dial(addr)
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)

        # Accessing these properties must not raise AttributeError or crash
        assert l.local_address is not None
        assert l.remote_address is None
        assert d.local_address is not None
        assert d.remote_address is not None


def test_v2_message_memory_safety():
    """Verify v2 Message frees memory on failure and handles __del__ safely."""
    with pytest.raises(Exception):
        v2.Message(None)
    gc.collect()

    # Valid message lifecycle
    msg = v2.Message(b"test data")
    assert msg.bytes == b"test data"
    del msg
    gc.collect()
