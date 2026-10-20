import pytest
import pynng
from conftest import random_addr, FAST_TIMEOUT


def test_recv_into_bytearray():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        s1.send(b"hello zero copy")
        buf = bytearray(32)
        nbytes = s2.recv_into(buf)
        assert nbytes == 15
        assert buf[:nbytes] == b"hello zero copy"


def test_recv_into_memoryview():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        s1.send(b"testing memoryview")
        buf = bytearray(64)
        mv = memoryview(buf)[10:30]
        nbytes = s2.recv_into(mv)
        assert nbytes == 18
        assert mv[:nbytes] == b"testing memoryview"
        assert buf[10 : 10 + nbytes] == b"testing memoryview"


def test_recv_into_truncated_to_buffer_size():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        s1.send(b"0123456789abcdef")
        buf = bytearray(5)
        nbytes = s2.recv_into(buf)
        assert nbytes == 5
        assert buf == b"01234"


def test_recv_into_readonly_raises_buffer_error():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        s1.send(b"test")
        with pytest.raises(BufferError, match="buffer must be writable"):
            s2.recv_into(b"read-only-bytes")


def test_recv_into_invalid_type_raises_type_error():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        s1.send(b"test")
        with pytest.raises(TypeError):
            s2.recv_into(12345)


def test_send_buffer_protocol():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        # bytearray
        s1.send(bytearray(b"from bytearray"))
        assert s2.recv() == b"from bytearray"

        # memoryview
        s1.send(memoryview(b"from memoryview"))
        assert s2.recv() == b"from memoryview"

        # invalid type
        with pytest.raises(ValueError):
            s1.send("string not allowed")
        with pytest.raises(TypeError):
            s1.send(999)


@pytest.mark.asyncio
async def test_arecv_into_asyncio():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        await s1.asend(bytearray(b"asyncio buffer data"))
        buf = bytearray(32)
        n = await s2.arecv_into(buf)
        assert n == 19
        assert buf[:n] == b"asyncio buffer data"

        # Read-only buffer check
        await s1.asend(b"check")
        with pytest.raises(BufferError, match="buffer must be writable"):
            await s2.arecv_into(b"read-only")


@pytest.mark.trio
async def test_arecv_into_trio():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s1, pynng.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s2:
        await s1.asend(memoryview(b"trio buffer data"))
        buf = bytearray(32)
        n = await s2.arecv_into(buf)
        assert n == 16
        assert buf[:n] == b"trio buffer data"


def test_context_recv_into():
    addr = random_addr()
    with pynng.Rep0(listen=addr, recv_timeout=FAST_TIMEOUT) as rep, pynng.Req0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as req:
        ctx_rep = rep.new_context()
        ctx_req = req.new_context()

        ctx_req.send(b"req into")
        buf = bytearray(20)
        n = ctx_rep.recv_into(buf)
        assert n == 8
        assert buf[:n] == b"req into"

        ctx_rep.send(b"rep into")
        buf2 = bytearray(20)
        n2 = ctx_req.recv_into(buf2)
        assert n2 == 8
        assert buf2[:n2] == b"rep into"


@pytest.mark.asyncio
async def test_context_arecv_into_asyncio():
    addr = random_addr()
    with pynng.Rep0(listen=addr, recv_timeout=FAST_TIMEOUT) as rep, pynng.Req0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as req:
        ctx_rep = rep.new_context()
        ctx_req = req.new_context()

        await ctx_req.asend(b"async req into")
        buf = bytearray(30)
        n = await ctx_rep.arecv_into(buf)
        assert n == 14
        assert buf[:n] == b"async req into"

        await ctx_rep.asend(b"async rep into")
        buf2 = bytearray(30)
        n2 = await ctx_req.arecv_into(buf2)
        assert n2 == 14
        assert buf2[:n2] == b"async rep into"
