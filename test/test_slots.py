"""Tests verifying __slots__ and absence of __dict__ on hot-path models."""

import pytest
import pynng
from pynng.service import Request
from pynng.stats import Stat
import pynng.sockaddr as sa


def test_message_slots():
    """Verify pynng.Message uses __slots__ and does not have __dict__."""
    msg = pynng.Message(b"payload")
    assert not hasattr(msg, "__dict__")
    assert "__slots__" in type(msg).__dict__
    assert "__slots__" in pynng._base.Message.__dict__
    assert msg.bytes == b"payload"
    assert msg.pipe is None
    with pytest.raises(AttributeError):
        msg._unslotted_dynamic_field = "leak"


def test_v2_message_slots():
    """Verify v2 Message uses __slots__ and does not have __dict__."""
    try:
        from pynng.v2 import nng as v2_nng
    except ImportError:
        pytest.skip("v2 not available")
    msg = v2_nng.Message(b"v2_payload")
    assert not hasattr(msg, "__dict__")
    assert "__slots__" in type(msg).__dict__
    assert msg.bytes == b"v2_payload"
    assert msg.pipe is None
    with pytest.raises(AttributeError):
        msg._unslotted_dynamic_field = "leak"


def test_service_request_slots():
    """Verify Request uses __slots__ and does not have __dict__."""
    req = Request(b"data", None)
    assert not hasattr(req, "__dict__")
    assert "__slots__" in type(req).__dict__
    assert req.data == b"data"
    assert req.context is None
    with pytest.raises(AttributeError):
        req._unslotted_dynamic_field = "leak"


def test_stat_slots():
    """Verify Stat dataclass uses slots=True and does not have __dict__."""
    stat = Stat(
        name="test_stat",
        desc="test description",
        type=0,
        unit=0,
        value=42,
        timestamp=1000,
        type_name="level",
        unit_name="none",
    )
    assert not hasattr(stat, "__dict__")
    assert "__slots__" in type(stat).__dict__
    assert stat.name == "test_stat"
    assert stat.value == 42
    assert stat["value"] == 42
    with pytest.raises(AttributeError):
        stat._unslotted_dynamic_field = "leak"


@pytest.mark.parametrize(
    "family,expected_cls",
    [
        (pynng.lib.NNG_AF_UNSPEC, sa.SockAddr),
        (pynng.lib.NNG_AF_INPROC, sa.InprocAddr),
        (pynng.lib.NNG_AF_IPC, sa.IPCAddr),
        (pynng.lib.NNG_AF_INET, sa.InAddr),
        (pynng.lib.NNG_AF_INET6, sa.In6Addr),
        (pynng.lib.NNG_AF_ZT, sa.ZTAddr),
        (pynng.lib.NNG_AF_ABSTRACT, sa.AbstractAddr),
    ],
)
def test_sockaddr_slots(family, expected_cls):
    """Verify SockAddr and every concrete address subclass define __slots__ and lack __dict__."""
    raw = pynng.ffi.new("nng_sockaddr *")
    raw.s_family = family
    addr = sa._nng_sockaddr(raw)
    assert type(addr) is expected_cls
    assert not hasattr(addr, "__dict__")
    assert "__slots__" in type(addr).__dict__
    assert addr.family == family
    assert addr.family_as_str == sa.SockAddr.type_to_str[family]
    with pytest.raises(AttributeError):
        addr._unslotted_dynamic_field = "leak"

