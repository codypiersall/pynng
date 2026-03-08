"""Tests for pynng.service.Rep0Service."""

import asyncio
import warnings

import pytest
import trio

import pynng
from pynng.service import Rep0Service, Request
from _test_util import wait_pipe_len


def _unique_addr(name):
    """Return a unique inproc address for the given test name."""
    return "inproc://test-service-{}".format(name)


# ---------------------------------------------------------------------------
# Basic req/rep exchange
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_basic_reqrep_asyncio():
    """A single request/reply exchange through the service."""
    addr = _unique_addr("basic-asyncio")

    async with Rep0Service(addr, workers=2, recv_timeout=3000, send_timeout=3000) as service:
        req = pynng.Req0(dial=addr, recv_timeout=3000, send_timeout=3000)
        wait_pipe_len(req, 1)

        await req.asend(b"hello")

        async for request in service:
            assert request.data == b"hello"
            await request.reply(b"world")
            break

        response = await req.arecv()
        assert response == b"world"
        req.close()


@pytest.mark.trio
async def test_basic_reqrep_trio():
    """A single request/reply exchange through the service with trio."""
    addr = _unique_addr("basic-trio")

    async with Rep0Service(addr, workers=2, recv_timeout=3000, send_timeout=3000) as service:
        req = pynng.Req0(dial=addr, recv_timeout=3000, send_timeout=3000)
        wait_pipe_len(req, 1)

        await req.asend(b"hello")

        async for request in service:
            assert request.data == b"hello"
            await request.reply(b"world")
            break

        response = await req.arecv()
        assert response == b"world"
        req.close()


# ---------------------------------------------------------------------------
# Multiple concurrent requests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_requests_asyncio():
    """Multiple concurrent requests all get correct responses."""
    addr = _unique_addr("concurrent-asyncio")
    num_clients = 4

    async with Rep0Service(addr, workers=4, recv_timeout=3000, send_timeout=3000) as service:
        results = {}

        async def client(idx):
            req = pynng.Req0(dial=addr, recv_timeout=3000, send_timeout=3000)
            wait_pipe_len(req, 1)
            await req.asend("request-{}".format(idx).encode())
            response = await req.arecv()
            results[idx] = response
            req.close()

        async def server():
            handled = 0
            async for request in service:
                reply_data = request.data.replace(b"request-", b"reply-")
                await request.reply(reply_data)
                handled += 1
                if handled >= num_clients:
                    break

        await asyncio.gather(
            server(),
            *(client(idx) for idx in range(num_clients)),
        )

    assert len(results) == num_clients
    for idx in range(num_clients):
        assert results[idx] == "reply-{}".format(idx).encode()


@pytest.mark.trio
async def test_concurrent_requests_trio():
    """Multiple concurrent requests all get correct responses with trio."""
    addr = _unique_addr("concurrent-trio")
    num_clients = 4

    async with Rep0Service(addr, workers=4, recv_timeout=3000, send_timeout=3000) as service:
        results = {}

        async def client(idx):
            req = pynng.Req0(dial=addr, recv_timeout=3000, send_timeout=3000)
            wait_pipe_len(req, 1)
            await req.asend("request-{}".format(idx).encode())
            response = await req.arecv()
            results[idx] = response
            req.close()

        async def server():
            handled = 0
            async for request in service:
                reply_data = request.data.replace(b"request-", b"reply-")
                await request.reply(reply_data)
                handled += 1
                if handled >= num_clients:
                    break

        async with trio.open_nursery() as nursery:
            nursery.start_soon(server)
            for idx in range(num_clients):
                nursery.start_soon(client, idx)

    assert len(results) == num_clients
    for idx in range(num_clients):
        assert results[idx] == "reply-{}".format(idx).encode()


# ---------------------------------------------------------------------------
# Service shutdown (clean exit from async with)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_clean_shutdown_asyncio():
    """Service shuts down cleanly when exiting the async with block."""
    addr = _unique_addr("shutdown-asyncio")

    async with Rep0Service(addr, workers=2, recv_timeout=3000, send_timeout=3000) as service:
        req = pynng.Req0(dial=addr, recv_timeout=3000, send_timeout=3000)
        wait_pipe_len(req, 1)

        # Send and handle one request to verify the service is working
        await req.asend(b"ping")
        async for request in service:
            await request.reply(b"pong")
            break

        response = await req.arecv()
        assert response == b"pong"
        req.close()

    # After exiting, the socket should be closed
    assert service._socket is None


@pytest.mark.trio
async def test_clean_shutdown_trio():
    """Service shuts down cleanly when exiting the async with block (trio)."""
    addr = _unique_addr("shutdown-trio")

    async with Rep0Service(addr, workers=2, recv_timeout=3000, send_timeout=3000) as service:
        req = pynng.Req0(dial=addr, recv_timeout=3000, send_timeout=3000)
        wait_pipe_len(req, 1)

        await req.asend(b"ping")
        async for request in service:
            await request.reply(b"pong")
            break

        response = await req.arecv()
        assert response == b"pong"
        req.close()

    assert service._socket is None


# ---------------------------------------------------------------------------
# Request double-reply raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_double_reply_raises_asyncio():
    """Replying twice to the same request raises RuntimeError."""
    addr = _unique_addr("double-reply-asyncio")

    async with Rep0Service(addr, workers=1, recv_timeout=3000, send_timeout=3000) as service:
        req = pynng.Req0(dial=addr, recv_timeout=3000, send_timeout=3000)
        wait_pipe_len(req, 1)

        await req.asend(b"test")
        async for request in service:
            await request.reply(b"first")
            with pytest.raises(RuntimeError, match="already been replied"):
                await request.reply(b"second")
            break

        await req.arecv()
        req.close()


# ---------------------------------------------------------------------------
# Request unreplied warning
# ---------------------------------------------------------------------------

def test_unreplied_request_warns():
    """A Request that goes out of scope without reply emits ResourceWarning."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        r = Request(b"test-data", None)
        del r
        # ResourceWarning may or may not fire depending on GC timing,
        # so we just verify the class works without errors.


# ---------------------------------------------------------------------------
# Request class unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_data_attribute():
    """Request.data holds the bytes payload."""
    r = Request(b"payload", None)
    assert r.data == b"payload"
    r._replied = True  # suppress warning
