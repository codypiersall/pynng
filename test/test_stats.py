import pynng
from conftest import random_addr, FAST_TIMEOUT


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

        # Dict access
        assert st1["name"] == "socket"
        assert st1["type_name"] == "scope"

        # Protocol stat
        proto = st1.find("protocol")
        assert proto is not None
        assert proto.value == "pair"
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
        # Before transmission
        s1.send(b"12345")
        s2.recv()

        st1 = s1.stats()
        st2 = s2.stats()

        tx_msgs = st1.find("tx_msgs")
        rx_msgs = st2.find("rx_msgs")
        assert tx_msgs is not None
        assert rx_msgs is not None
        # Counters should be positive or non-negative
        assert tx_msgs.value >= 0
        assert rx_msgs.value >= 0


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
