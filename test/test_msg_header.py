import pytest
import pynng
from conftest import random_addr, FAST_TIMEOUT


def test_message_header_default():
    msg = pynng.Message(b"payload")
    assert msg.header == b""
    assert msg.bytes == b"payload"


def test_message_header_append_and_clear():
    msg = pynng.Message(b"payload")
    msg.header_append(b"header1")
    assert msg.header == b"header1"

    # append bytearray
    msg.header_append(bytearray(b"_header2"))
    assert msg.header == b"header1_header2"

    # append memoryview
    msg.header_append(memoryview(b"_header3"))
    assert msg.header == b"header1_header2_header3"

    # clear header
    msg.header_clear()
    assert msg.header == b""


def test_message_header_chop_and_trim():
    msg = pynng.Message(b"payload")
    msg.header_append(b"1234567890")
    assert msg.header == b"1234567890"

    # Chop 3 bytes from end
    msg.header_chop(3)
    assert msg.header == b"1234567"

    # Trim 2 bytes from start
    msg.header_trim(2)
    assert msg.header == b"34567"


def test_message_copy_and_dup():
    msg = pynng.Message(b"original body")
    msg.header_append(b"original header")

    cp = msg.copy()
    dp = msg.dup()

    assert cp.bytes == b"original body"
    assert cp.header == b"original header"
    assert dp.bytes == b"original body"
    assert dp.header == b"original header"

    # Independent modification
    cp.header_append(b"-extra")
    assert msg.header == b"original header"
    assert cp.header == b"original header-extra"


def test_message_header_and_copy_after_send():
    address = random_addr()
    with pynng.Pair0(listen=address) as s1, pynng.Pair0(dial=address) as s2:
        msg = pynng.Message(b"hello")
        msg.header_append(b"hdr")
        s1.send_msg(msg)

        # Once sent, accessing header or copying must raise MessageStateError
        with pytest.raises(pynng.MessageStateError):
            _ = msg.header

        with pytest.raises(pynng.MessageStateError):
            msg.header_append(b"more")

        with pytest.raises(pynng.MessageStateError):
            msg.copy()

        recvd = s2.recv_msg()
        assert b"hello" in recvd.bytes


def test_message_init_buffer_protocol():
    msg1 = pynng.Message(bytearray(b"bytearray data"))
    assert msg1.bytes == b"bytearray data"

    msg2 = pynng.Message(memoryview(b"memoryview data"))
    assert msg2.bytes == b"memoryview data"

    with pytest.raises(ValueError):
        pynng.Message("strings not allowed")

    with pytest.raises(TypeError):
        pynng.Message(12345)
