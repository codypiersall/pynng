import pynng


addr = 'tcp://127.0.0.1:13131'
addr2 = 'tcp://127.0.0.1:13132'


def test_dialers_get_added():
    with pynng.Pair0() as s:
        assert len(s.dialers) == 0
        s.dial(addr, block=False)
        assert len(s.dialers) == 1
        s.dial(addr2, block=False)
        assert len(s.dialers) == 2


def test_listeners_get_added():
    with pynng.Pair0() as s:
        assert len(s.listeners) == 0
        s.listen(addr)
        assert len(s.listeners) == 1
        s.listen(addr2)
        assert len(s.listeners) == 2


def test_closing_listener_works():
    with pynng.Pair0(listen=addr) as s:
        assert len(s.listeners) == 1
        s.listeners[0].close()
        assert len(s.listeners) == 0
        # if the listener is really closed, we should be able to listen at the
        # same address again
        s.listen(addr)
        assert len(s.listeners) == 1
    assert len(s.listeners) == 0


def test_closing_dialer_works():
    with pynng.Pair0(dial=addr, block_on_dial=False) as s:
        assert len(s.dialers) == 1
        s.dialers[0].close()
    assert len(s.listeners) == 0

