import pynng as nng
import pytest
import time

# TODO: all sockets need timeouts


addr = 'tcp://127.0.0.1:13131'


def test_context_manager_works():
    # we have to grab a reference to the sockets so garbage collection doesn't
    # close the socket for us automatically.
    with nng.Pair0(listen=addr) as s0:  # noqa
        pass
    # we should be able to do it again if the context manager worked
    with nng.Pair0(listen=addr) as s1:  # noqa
        pass


def test_timeout_works():
    with nng.Pair0(listen=addr) as s0:
        # default is -1
        assert s0.recv_timeout == -1
        s0.recv_timeout = 1  # 1 ms, not too long
        with pytest.raises(Exception):  # TODO: better exception
            s0.recv()


def test_pair0():
    with nng.Pair0(listen=addr, recv_timeout=100) as s0, \
            nng.Pair0(dial=addr, recv_timeout=100) as s1:
        val = b'oaisdjfa'
        s1.send(val)
        assert s0.recv() == val


def test_pair1():
    with nng.Pair1(listen=addr, recv_timeout=100) as s0, \
            nng.Pair1(dial=addr, recv_timeout=100) as s1:
        val = b'oaisdjfa'
        s1.send(val)
        assert s0.recv() == val


def test_reqrep0():
    with nng.Req0(listen=addr, recv_timeout=100) as req, \
            nng.Rep0(dial=addr, recv_timeout=100) as rep:

        request = b'i am requesting'
        req.send(request)
        assert rep.recv() == request

        response = b'i am responding'
        rep.send(response)
        assert req.recv() == response

        # TODO: when changing exceptions elsewhere, change here!
        # requesters can't receive before sending
        with pytest.raises(Exception):
            req.recv()

        # responders can't send before receiving
        with pytest.raises(Exception):
            rep.send()


def test_pubsub0():
    with nng.Sub0(listen=addr, recv_timeout=100) as sub, \
            nng.Pub0(dial=addr, recv_timeout=100) as pub:
        sub.subscribe(b'')

        request = b'i am requesting'
        time.sleep(0.01)
        pub.send(request)
        assert sub.recv() == request

        # TODO: when changing exceptions elsewhere, change here!
        # publishers can't recv
        with pytest.raises(Exception):
            pub.recv()

        # responders can't send before receiving
        with pytest.raises(Exception):
            sub.send()


def test_cannot_instantiate_socket_without_opener():
    with pytest.raises(TypeError):
        nng.Socket()


def test_can_instantiate_socket_with_raw_opener():
    with nng.Socket(opener=nng.nng.nng_sub0_open_raw):
        pass

