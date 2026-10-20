"""Tests for async ergonomic improvements to pynng.

Covers:
- __aiter__ / __anext__ on Socket and Context
- async with (aenter/aexit) on Socket and Context
- aclose() on Socket and Context
- get_running_loop() usage (implicitly tested by all asyncio tests)
- Defensive _aio_map.pop in _async_complete
"""

import asyncio
import unittest.mock

import pytest
import trio

import pynng
from pynng import _aio

from conftest import random_addr, FAST_TIMEOUT, MEDIUM_TIMEOUT, SLOW_TIMEOUT


# ---------------------------------------------------------------------------
# Socket: async for
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_socket_async_for_trio():
    """async for on a socket receives messages until socket is closed."""
    addr = random_addr()
    received = []

    listener = pynng.Push0(listen=addr, send_timeout=MEDIUM_TIMEOUT)
    puller = pynng.Pull0(dial=addr, recv_timeout=MEDIUM_TIMEOUT)
    try:
        recv_done = trio.Event()

        async with trio.open_nursery() as nursery:
            async def send_messages():
                for i in range(3):
                    await listener.asend(f"msg{i}".encode())
                await recv_done.wait()
                puller.close()

            nursery.start_soon(send_messages)

            async for msg in puller:
                received.append(msg)
                if len(received) == 3:
                    recv_done.set()
    finally:
        puller.close()
        listener.close()

    assert len(received) == 3
    assert received[0] == b"msg0"
    assert received[1] == b"msg1"
    assert received[2] == b"msg2"


@pytest.mark.trio
async def test_socket_async_for_stops_on_close_trio():
    """async for stops cleanly when socket is closed externally."""
    addr = random_addr()
    received = []

    pusher = pynng.Push0(listen=addr, send_timeout=MEDIUM_TIMEOUT)
    puller = pynng.Pull0(dial=addr, recv_timeout=SLOW_TIMEOUT)
    try:
        recv_done = trio.Event()

        async with trio.open_nursery() as nursery:
            async def send_and_close():
                await pusher.asend(b"hello")
                await recv_done.wait()
                puller.close()

            nursery.start_soon(send_and_close)

            async for msg in puller:
                received.append(msg)
                recv_done.set()
    finally:
        puller.close()
        pusher.close()

    assert received == [b"hello"]



# ---------------------------------------------------------------------------
# Socket: async with
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_socket_async_with_trio():
    """async with on a socket closes it on exit."""
    addr = random_addr()
    async with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s:
        assert isinstance(s, pynng.Socket)
        async with pynng.Pair0(dial=addr, send_timeout=FAST_TIMEOUT) as d:
            await d.asend(b"hi")
            assert await s.arecv() == b"hi"
    # After exiting, socket should be closed (listeners cleared)
    assert len(s._listeners) == 0
    # Verify NNG-level closure: any operation on a closed socket raises Closed
    with pytest.raises(pynng.Closed):
        s.recv()


@pytest.mark.trio
async def test_socket_async_with_cleans_up_on_exception_trio():
    """async with on a socket closes it even if an exception occurs."""
    addr = random_addr()
    with pytest.raises(RuntimeError, match="intentional"):
        async with pynng.Pair0(listen=addr) as s:
            raise RuntimeError("intentional")
    assert len(s._listeners) == 0


# ---------------------------------------------------------------------------
# Socket: aclose
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_socket_aclose_trio():
    """aclose() closes the socket."""
    addr = random_addr()
    s = pynng.Pair0(listen=addr)
    assert len(s.listeners) == 1
    await s.aclose()
    assert len(s._listeners) == 0
    # Verify NNG-level closure: any operation on a closed socket raises Closed
    with pytest.raises(pynng.Closed):
        s.recv()


# ---------------------------------------------------------------------------
# Context: async for
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_context_async_for_trio():
    """async for on a context receives messages."""
    addr = random_addr()
    received = []
    with pynng.Rep0(listen=addr, recv_timeout=MEDIUM_TIMEOUT) as rep_sock, \
         pynng.Req0(dial=addr, recv_timeout=MEDIUM_TIMEOUT) as req_sock:
        ctx_rep = rep_sock.new_context()
        ctx_req = req_sock.new_context()

        # Send a request so rep can receive it
        await ctx_req.asend(b"request1")

        # Use async for on the rep context (just one iteration, then break)
        async for msg in ctx_rep:
            received.append(msg)
            # Send response so req/rep cycle completes
            await ctx_rep.asend(b"response1")
            break

        resp = await ctx_req.arecv()
        assert resp == b"response1"

        ctx_rep.close()
        ctx_req.close()

    assert received == [b"request1"]


@pytest.mark.trio
async def test_context_async_for_stops_on_close_trio():
    """async for on a context stops when the parent socket is closed."""
    addr = random_addr()
    received = []

    rep_sock = pynng.Rep0(listen=addr, recv_timeout=SLOW_TIMEOUT)
    req_sock = pynng.Req0(dial=addr, send_timeout=MEDIUM_TIMEOUT)
    try:
        ctx = rep_sock.new_context()
        recv_done = trio.Event()

        async with trio.open_nursery() as nursery:
            async def send_and_close():
                await req_sock.asend(b"msg")
                await recv_done.wait()
                # Closing the parent socket causes the context's arecv to get
                # a Closed exception, which stops async iteration.
                rep_sock.close()

            nursery.start_soon(send_and_close)

            async for msg in ctx:
                received.append(msg)
                recv_done.set()
    finally:
        req_sock.close()
        rep_sock.close()

    assert received == [b"msg"]



# ---------------------------------------------------------------------------
# Context: async with
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_context_async_with_trio():
    """async with on a context closes it on exit."""
    addr = random_addr()
    with pynng.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as req_sock, \
         pynng.Rep0(dial=addr, recv_timeout=FAST_TIMEOUT) as rep_sock:
        async with req_sock.new_context() as ctx_req:
            assert isinstance(ctx_req, pynng.Context)
            async with rep_sock.new_context() as ctx_rep:
                await ctx_req.asend(b"hello")
                assert await ctx_rep.arecv() == b"hello"
                await ctx_rep.asend(b"world")
                assert await ctx_req.arecv() == b"world"
            # ctx_rep should be closed now
            assert ctx_rep._context is None
            ctx_rep.close()  # Second close must not raise


# ---------------------------------------------------------------------------
# Context: aclose
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_context_aclose_trio():
    """aclose() closes the context."""
    with pynng.Req0() as s:
        ctx = s.new_context()
        assert ctx._context is not None
        await ctx.aclose()
        assert ctx._context is None
        ctx.close()  # Second close must not raise


# ---------------------------------------------------------------------------
# Defensive _aio_map.pop
# ---------------------------------------------------------------------------

def test_aio_map_pop_defensive():
    """_async_complete does not raise if callback id is not in _aio_map.

    This tests the defensive pop(id, None) behavior. We simulate calling the
    callback with a void* that has no corresponding entry.
    """
    from pynng._nng import ffi, lib

    # Create a fake void* pointer that maps to an id not in _aio_map
    fake_id = 9999999999
    void_p = ffi.cast("void *", fake_id)

    # Ensure this id is NOT in the map
    _aio._aio_map.pop(fake_id, None)

    # This should not raise (before the fix, it would KeyError)
    lib._async_complete(void_p)


# ---------------------------------------------------------------------------
# get_running_loop verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_asyncio_uses_running_loop():
    """Verify asyncio_helper calls get_running_loop (not get_event_loop).

    Patches get_event_loop at the pynng._aio module level to raise if called,
    ensuring that the code path uses get_running_loop instead.
    """
    addr = random_addr()
    with unittest.mock.patch.object(
        _aio.asyncio,
        "get_event_loop",
        side_effect=AssertionError("get_event_loop should not be called"),
    ):
        with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as listener, \
             pynng.Pair0(dial=addr, send_timeout=FAST_TIMEOUT) as dialer:
            await dialer.asend(b"running-loop-test")
            result = await listener.arecv()
            assert result == b"running-loop-test"


# --- Dialer/Listener async context manager tests ---


@pytest.mark.trio
async def test_dialer_async_context_manager_trio():
    """Dialer can be used as an async context manager with trio."""
    addr = random_addr()
    with pynng.Pair0(listen=addr) as listener_sock:
        with pynng.Pair0() as dialer_sock:
            dialer = dialer_sock.dial(addr, block=True)
            async with dialer:
                await dialer_sock.asend(b"hello from dialer")
                assert (await listener_sock.arecv()) == b"hello from dialer"
            # after exiting async with, dialer is closed


@pytest.mark.trio
async def test_listener_async_context_manager_trio():
    """Listener can be used as an async context manager with trio."""
    addr = random_addr()
    with pynng.Pair0() as sock:
        async with sock.listen(addr) as listener:
            assert listener is not None
        # after exiting async with, listener is closed


@pytest.mark.trio
async def test_dialer_aclose_trio():
    """Dialer.aclose() works correctly and verifies closed state."""
    addr = random_addr()
    with pynng.Pair0(listen=addr) as listener_sock:
        with pynng.Pair0() as dialer_sock:
            dialer = dialer_sock.dial(addr, block=True)
            await dialer.aclose()
            assert dialer.id not in dialer_sock._dialers
            # Calling aclose again should be idempotent (no error)
            await dialer.aclose()


@pytest.mark.trio
async def test_listener_aclose_trio():
    """Listener.aclose() works correctly with trio and verifies closed state."""
    addr = random_addr()
    with pynng.Pair0() as sock:
        listener = sock.listen(addr)
        await listener.aclose()
        assert listener.id not in sock._listeners
        # Calling aclose again should be idempotent (no error)
        await listener.aclose()


@pytest.mark.asyncio
async def test_dialer_async_context_manager_asyncio():
    """Dialer can be used as an async context manager with asyncio."""
    addr = random_addr()
    with pynng.Pair0(listen=addr) as listener_sock:
        with pynng.Pair0() as dialer_sock:
            dialer = dialer_sock.dial(addr, block=True)
            async with dialer:
                await dialer_sock.asend(b"hello from dialer")
                assert (await listener_sock.arecv()) == b"hello from dialer"


@pytest.mark.asyncio
async def test_listener_async_context_manager_asyncio():
    """Listener can be used as an async context manager with asyncio."""
    addr = random_addr()
    with pynng.Pair0() as sock:
        async with sock.listen(addr) as listener:
            assert listener is not None


@pytest.mark.asyncio
async def test_dialer_aclose_asyncio():
    """Dialer.aclose() works correctly with asyncio and verifies closed state."""
    addr = random_addr()
    with pynng.Pair0(listen=addr) as listener_sock:
        with pynng.Pair0() as dialer_sock:
            dialer = dialer_sock.dial(addr, block=True)
            await dialer.aclose()
            assert dialer.id not in dialer_sock._dialers
            # Calling aclose again should be idempotent (no error)
            await dialer.aclose()


@pytest.mark.asyncio
async def test_listener_aclose_asyncio():
    """Listener.aclose() works correctly with asyncio and verifies closed state."""
    addr = random_addr()
    with pynng.Pair0() as sock:
        listener = sock.listen(addr)
        await listener.aclose()
        assert listener.id not in sock._listeners
        # Calling aclose again should be idempotent (no error)
        await listener.aclose()

