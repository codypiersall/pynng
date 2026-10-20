import pytest
import pynng
from conftest import random_addr, FAST_TIMEOUT


RAW_CLASSES = [
    pynng.RawBus0,
    pynng.RawPair0,
    pynng.RawPair1,
    pynng.RawPush0,
    pynng.RawPull0,
    pynng.RawPub0,
    pynng.RawSub0,
    pynng.RawReq0,
    pynng.RawRep0,
    pynng.RawSurveyor0,
    pynng.RawRespondent0,
]

COOKED_CLASSES = [
    pynng.Bus0,
    pynng.Pair0,
    pynng.Pair1,
    pynng.Push0,
    pynng.Pull0,
    pynng.Pub0,
    pynng.Sub0,
    pynng.Req0,
    pynng.Rep0,
    pynng.Surveyor0,
    pynng.Respondent0,
]


@pytest.mark.parametrize("cls", RAW_CLASSES)
def test_raw_socket_instantiation(cls):
    with cls() as s:
        assert isinstance(s, pynng.Socket)
        assert s.raw is True


@pytest.mark.parametrize("cls", COOKED_CLASSES)
def test_socket_raw_parameter(cls):
    with cls(raw=True) as s:
        assert isinstance(s, pynng.Socket)
        assert s.raw is True

    with cls(raw=False) as s:
        assert isinstance(s, pynng.Socket)
        assert s.raw is False


def test_raw_req_rep_routing_headers():
    addr = random_addr()
    with pynng.RawRep0(listen=addr, recv_timeout=FAST_TIMEOUT) as rep, pynng.Req0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as req:
        req.send(b"request from cooked req")

        # In raw REP, recv_msg() has a non-empty header containing routing backtrace
        msg = rep.recv_msg()
        assert msg.bytes == b"request from cooked req"
        assert len(msg.header) > 0

        # Sending the message back using the same header routes back to client
        reply_msg = pynng.Message(b"reply to cooked req")
        reply_msg.header_append(msg.header)
        rep.send_msg(reply_msg)

        reply = req.recv()
        assert reply == b"reply to cooked req"
