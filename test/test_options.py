import pynng as nng
import pytest

# TODO: all sockets need timeouts


addr = 'tcp://127.0.0.1:13131'


def test_timeout_works():
    with nng.Pair0(listen=addr) as s0:
        # default is -1
        assert s0.recv_timeout == -1
        s0.recv_timeout = 1  # 1 ms, not too long
        with pytest.raises(nng.exceptions.Timeout):
            s0.recv()


def test_can_set_socket_name():
    with nng.Pair0() as p:
        assert p.name != 'this'
        p.name = 'this'
        assert p.name == 'this'
        # make sure we're actually testing the right thing
        assert p._getopt_string('socket-name') == 'this'


def test_can_read_sock_raw():
    with nng.Pair0() as cooked, \
            nng.Pair0(opener=nng.lib.nng_pair0_open_raw) as raw:
        assert not cooked.raw
        assert raw.raw
