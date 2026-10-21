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
    assert hasattr(msg, "__slots__")
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
    assert hasattr(msg, "__slots__")
    with pytest.raises(AttributeError):
        msg._unslotted_dynamic_field = "leak"


def test_service_request_slots():
    """Verify Request uses __slots__ and does not have __dict__."""
    req = Request(b"data", None)
    assert not hasattr(req, "__dict__")
    assert hasattr(req, "__slots__")
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
    assert hasattr(stat, "__slots__")
    with pytest.raises(AttributeError):
        stat._unslotted_dynamic_field = "leak"


def test_sockaddr_slots():
    """Verify SockAddr and its address subclasses use __slots__."""
    base_addr = sa.SockAddr(None)
    assert not hasattr(base_addr, "__dict__")
    assert hasattr(base_addr, "__slots__")
    with pytest.raises(AttributeError):
        base_addr._unslotted_dynamic_field = "leak"

    raw = pynng.ffi.new("nng_sockaddr *")
    raw.s_family = pynng.lib.NNG_AF_INPROC
    inproc = sa.InprocAddr(raw)
    assert not hasattr(inproc, "__dict__")
    assert hasattr(inproc, "__slots__")
    with pytest.raises(AttributeError):
        inproc._unslotted_dynamic_field = "leak"
