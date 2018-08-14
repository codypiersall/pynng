import pynng as nng
import pytest
import time

# TODO: all sockets need timeouts


addr = 'tcp://127.0.0.1:13131'


def test_can_do_timeout():
    s0 = nng.Pair0(listen=addr)
    # default is -1
    assert s0.recv_timeout == -1
    s0.recv_timeout = 1  # 1 ms, not too long
    with pytest.raises(Exception):  # TODO: better exception
        s0.recv()
    s0.close()


def test_pair0():
    s0 = nng.Pair0(listen=addr, recv_timeout=100)
    s1 = nng.Pair0(dial=addr, recv_timeout=100)

    val = b'oaisdjfa'
    s1.send(val)
    assert s0.recv() == val
    s0.close()
    s1.close()


def test_pair1():
    s0 = nng.Pair1(listen=addr, recv_timeout=100)
    s1 = nng.Pair1(dial=addr, recv_timeout=100)

    val = b'oaisdjfa'
    s1.send(val)
    assert s0.recv() == val
    s0.close()
    s1.close()


def test_reqrep0():
    req = nng.Req0(listen=addr, recv_timeout=100)
    rep = nng.Rep0(dial=addr, recv_timeout=100)

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
    req.close()
    rep.close()


def test_pubsub0():
    sub = nng.Sub0(listen=addr, recv_timeout=100)
    sub.subscribe(b'')
    pub = nng.Pub0(dial=addr, recv_timeout=100)

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
    pub.close()
    sub.close()
