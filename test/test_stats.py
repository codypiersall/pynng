import pytest
import pynng
from conftest import random_addr, FAST_TIMEOUT

try:
    pynng.stats()
except pynng.exceptions.NotSupported:
    pytest.skip("NNG compiled without stats support", allow_module_level=True)


def test_socket_stats_basic():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        st1 = s1.stats()
        assert isinstance(st1, pynng.Stat)
        assert st1.name == "socket"
        assert st1.type_name == "scope"
        assert st1.unit_name == "none"
        assert isinstance(st1.children, list)
        assert len(st1.children) > 0

        # Dict access: direct child stats take precedence over parent attributes
        assert st1["type_name"] == "scope"
        assert isinstance(st1["name"], pynng.Stat)
        assert st1["name"].name == "name"

        # Protocol stat
        proto = st1.find("protocol")
        assert proto is not None
        assert proto.value == "pair"
        assert proto["name"] == "protocol"
        assert proto["value"] == "pair"

        # as_dict() structure
        d = st1.as_dict()
        assert isinstance(d, dict)
        assert d["name"] == "socket"
        assert isinstance(d["children"], list)


def test_socket_stats_counters():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        s1.send(b"12345")
        assert s2.recv() == b"12345"

        st1 = pynng.socket_stats(s1)
        st2 = s2.stats()

        assert s1.stat("protocol") == "pair"
        with pytest.raises(KeyError):
            s1.stat("nonexistent_stat_key")
        with pytest.raises(KeyError):
            s1.stat("children")
        with pytest.raises(KeyError):
            _ = st1["find"]

        tx_msgs = st1.find("tx_msgs")
        rx_msgs = st2.find("rx_msgs")
        assert tx_msgs is not None
        assert rx_msgs is not None
        assert isinstance(tx_msgs.value, int)
        assert isinstance(rx_msgs.value, int)
        if tx_msgs.value > 0 or rx_msgs.value > 0:
            assert tx_msgs.value == 1
            assert rx_msgs.value == 1


def test_global_stats():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1:
        gst = pynng.stats()
        assert isinstance(gst, pynng.Stat)
        assert gst.type_name == "scope"
        assert isinstance(gst.children, list)

        # find_all across global tree
        sockets = gst.find_all("socket")
        assert len(sockets) >= 1

        d = gst.as_dict()
        assert "children" in d


def test_stat_repr():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1:
        st = s1.stats()
        r = repr(st)
        assert "Stat(name='socket'" in r
