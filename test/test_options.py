import os
import socket
import sys

import pynng
import pynng.options
import pytest
from pathlib import Path
from _test_util import wait_pipe_len
from conftest import random_addr, SHORT_TIMEOUT, FAST_TIMEOUT, MEDIUM_TIMEOUT, SLOW_TIMEOUT

tcp_addr = "tcp://127.0.0.1:0"


def test_timeout_works():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0:
        # default is -1
        assert s0.recv_timeout == -1
        s0.recv_timeout = 1  # 1 ms, not too long
        with pytest.raises(pynng.Timeout):
            s0.recv()


def test_can_set_socket_name():
    with pynng.Pair0() as p:
        assert p.name != "this"
        p.name = "this"
        assert p.name == "this"
        # make sure we're actually testing the right thing, not just setting an
        # attribute on the socket
        assert pynng.options._getopt_string(p, "socket-name") == "this"


def test_can_read_sock_raw():
    with pynng.Pair0() as cooked, pynng.Pair0(
        opener=pynng.lib.nng_pair0_open_raw
    ) as raw:
        assert not cooked.raw
        assert raw.raw


def test_dial_blocking_behavior():
    addr = random_addr()
    # the default dial is different than the pynng library; it will log in the
    # event of a failure, but then continue.
    with pynng.Pair1() as s0, pynng.Pair1(recv_timeout=MEDIUM_TIMEOUT) as s1:
        with pytest.raises(pynng.ConnectionRefused):
            s0.dial(addr, block=True)

        # default is to attempt
        s0.dial(addr)
        s1.listen(addr)
        wait_pipe_len(s0, 1)
        s0.send(b"what a message")
        assert s1.recv() == b"what a message"


def test_can_set_recvmaxsize():
    with pynng.Pair1(
        recv_timeout=FAST_TIMEOUT, recv_max_size=100, listen=tcp_addr
    ) as s0:
        actual_addr = f"tcp://{s0.listeners[0].local_address}"
        with pynng.Pair1(dial=actual_addr, send_timeout=FAST_TIMEOUT) as s1:
            wait_pipe_len(s0, 1)
            listener = s0.listeners[0]
            assert listener.recv_max_size == s0.recv_max_size
            # Verify right-sized messages get through
            small_msg = b"\0" * 50
            s1.send(small_msg)
            assert s0.recv() == small_msg
            # Verify oversized messages are dropped
            big_msg = b"\0" * 101
            s1.send(big_msg)
            with pytest.raises(pynng.Timeout):
                s0.recv()


def test_nng_sockaddr():
    with pynng.Pair1(recv_timeout=SHORT_TIMEOUT, listen=tcp_addr) as s0:
        sa = s0.listeners[0].local_address
        assert isinstance(sa, pynng.sockaddr.InAddr)
        # port is in network byte order (big-endian); verify it was assigned
        assigned_port = socket.ntohs(sa.port)
        assert assigned_port > 0
        # addr is big-endian 127.0.0.1
        expected_addr = 127 | 0 << 8 | 0 << 16 | 1 << 24
        assert expected_addr == sa.addr
        assert str(sa) == f"127.0.0.1:{assigned_port}"

    path = "/tmp/thisisipc"
    with pynng.Pair1(recv_timeout=SHORT_TIMEOUT, listen=f"ipc://{path}") as s0:
        sa = s0.listeners[0].local_address
        assert isinstance(sa, pynng.sockaddr.IPCAddr)
        assert sa.path == path
        assert str(sa) == path
    try:
        os.unlink(path)
    except OSError:
        pass

    url = random_addr()
    with pynng.Pair1(recv_timeout=SHORT_TIMEOUT, listen=url) as s0:
        sa = s0.listeners[0].local_address
        assert str(sa) == url

    # skip ipv6 test when running in Docker
    if Path("/.dockerenv").exists():
        pytest.skip("IPv6 unavailable in Docker")

    ipv6 = "tcp://[::1]:0"
    with pynng.Pair1(recv_timeout=SHORT_TIMEOUT, listen=ipv6) as s0:
        sa = s0.listeners[0].local_address
        assert isinstance(sa, pynng.sockaddr.In6Addr)
        assert sa.addr == b"\x00" * 15 + b"\x01"
        assigned_port = socket.ntohs(sa.port)
        assert assigned_port > 0
        assert str(sa) == f"[::1]:{assigned_port}"


def test_resend_time():
    addr = random_addr()
    # test req/rep resend time
    with pynng.Rep0(listen=addr, recv_timeout=MEDIUM_TIMEOUT) as rep, pynng.Req0(
        dial=addr, recv_timeout=MEDIUM_TIMEOUT, resend_time=100
    ) as req:
        sent = b"hey i have a question for you"
        req.send(sent)
        first = rep.recv()
        assert first == sent
        # if it doesn't resend we'll never receive the second time
        second = rep.recv()
        assert second == sent
        response = b"well i have an answer"
        rep.send(response)
        assert req.recv() == response


def test_setopt_rejects_non_integer_float():
    with pynng.Pair0() as s:
        with pytest.raises(ValueError):
            s.recv_timeout = 1.5  # not an integer-like float
        # But integer-like floats should work
        s.recv_timeout = 1.0
        assert s.recv_timeout == 1


def test_sockaddr_option_is_readonly():
    """SockAddrOption has no setter, so writing should raise TypeError."""
    with pynng.Pair1(recv_timeout=SHORT_TIMEOUT, listen=tcp_addr) as s0:
        listener = s0.listeners[0]
        with pytest.raises(TypeError):
            listener.local_address = "something"


def test_pointer_option_is_writeonly():
    """PointerOption has no getter, so reading tls_config should raise TypeError."""
    with pynng.Pair0() as s:
        with pytest.raises(TypeError):
            _ = s.tls_config


@pytest.mark.skipif(sys.platform == "win32", reason="select.select() may not work with NNG fds on Windows")
def test_recv_send_fd():
    """Test recv_fd and send_fd return valid file descriptors for polling."""
    import select
    from _test_util import wait_pipe_len
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=SLOW_TIMEOUT) as s0, \
         pynng.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        fd = s0.recv_fd
        assert isinstance(fd, int)
        assert fd >= 0
        sfd = s0.send_fd
        assert isinstance(sfd, int)
        assert sfd >= 0
        # Functional: send data, then poll recv_fd for readability
        s1.send(b"hello")
        readable, _, _ = select.select([s0.recv_fd], [], [], 5.0)
        assert readable, "recv_fd was not readable after peer sent data"
        data = s0.recv()
        assert data == b"hello"
