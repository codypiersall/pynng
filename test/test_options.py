import pynng
import pytest

# TODO: all sockets need timeouts


addr = 'tcp://127.0.0.1:13131'


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
        # make sure we're actually testing the right thing
        assert p._getopt_string('socket-name') == 'this'


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
