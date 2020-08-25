import pynng.options
import pytest
from pathlib import Path

PORT = 13131
IP = '127.0.0.1'
tcp_addr = 'tcp://{}:{}'.format(IP, PORT)
addr = 'inproc://test-addr'


def test_timeout_works():
    with pynng.Pair0(listen=addr) as s0:
        # default is -1
        assert s0.recv_timeout == -1
        s0.recv_timeout = 1  # 1 ms, not too long
        with pytest.raises(pynng.Timeout):
            s0.recv()


def test_can_set_socket_name():
    with pynng.Pair0() as p:
        assert p.name != 'this'
        p.name = 'this'
        assert p.name == 'this'
        # make sure we're actually testing the right thing, not just setting an
        # attribute on the socket
        assert pynng.options._getopt_string(p, 'socket-name') == 'this'


def test_can_read_sock_raw():
    with pynng.Pair0() as cooked, \
            pynng.Pair0(opener=pynng.lib.nng_pair0_open_raw) as raw:
        assert not cooked.raw
        assert raw.raw


def test_dial_blocking_behavior():
    # the default dial is different than the pynng library; it will log in the
    # event of a failure, but then continue.
    with pynng.Pair1() as s0, pynng.Pair1() as s1:
        with pytest.raises(pynng.ConnectionRefused):
            s0.dial(addr, block=True)

        # default is to attempt
        s0.dial(addr)
        s1.listen(addr)
        s0.send(b'what a message')
        assert s1.recv() == b'what a message'


def test_can_set_recvmaxsize():
    with pynng.Pair1(
            recv_timeout=50,
            recv_max_size=100,
            listen=tcp_addr) as s0, \
            pynng.Pair1(dial=tcp_addr) as s1:
        listener = s0.listeners[0]
        msg = b'\0' * 101
        assert listener.recv_max_size == s0.recv_max_size
        s1.send(msg)
        with pytest.raises(pynng.Timeout):
            s0.recv()


def test_nng_sockaddr():
    with pynng.Pair1(recv_timeout=50, listen=tcp_addr) as s0:
        sa = s0.listeners[0].local_address
        assert isinstance(sa, pynng.sockaddr.InAddr)
        # big-endian
        expected_port = (PORT >> 8) | ((PORT & 0xff) << 8)
        assert sa.port == expected_port
        # big-endian
        ip_parts = [int(x) for x in IP.split('.')]
        expected_addr = (
            ip_parts[0] |
            ip_parts[1] << 8 |
            ip_parts[2] << 16 |
            ip_parts[3] << 24
        )
        assert expected_addr == sa.addr
        assert str(sa) == tcp_addr.replace('tcp://', '')

    path = '/tmp/thisisipc'
    with pynng.Pair1(recv_timeout=50, listen='ipc://{}'.format(path)) as s0:
        sa = s0.listeners[0].local_address
        assert isinstance(sa, pynng.sockaddr.IPCAddr)
        assert sa.path == path
        assert str(sa) == path

    url = 'inproc://thisisinproc'
    with pynng.Pair1(recv_timeout=50, listen=url) as s0:
        sa = s0.listeners[0].local_address
        assert str(sa) == url

    # skip ipv6 test when running in Docker
    if Path('/.dockerenv').exists():
        return

    ipv6 = 'tcp://[::1]:13131'
    with pynng.Pair1(recv_timeout=50, listen=ipv6) as s0:
        sa = s0.listeners[0].local_address
        assert isinstance(sa, pynng.sockaddr.In6Addr)
        assert sa.addr == b'\x00' * 15 + b'\x01'
        assert str(sa) == ipv6.replace('tcp://', '')


def test_resend_time():
    # test req/rep resend time
    with pynng.Rep0(listen=addr, recv_timeout=3000) as rep, \
            pynng.Req0(dial=addr, recv_timeout=3000, resend_time=100) as req:
        req.send(b'hey i have a question for you')
        rep.recv()
        # if it doesn't resend we'll never receive the second time
        rep.recv()
        rep.send(b'well i have an answer')
        req.recv()
