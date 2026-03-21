"""Tests for async ergonomics: async context managers for Dialer and Listener."""

import pytest
import trio

import pynng

addr = "inproc://test-async-ergonomics"


@pytest.mark.trio
async def test_dialer_async_context_manager_trio():
    """Dialer can be used as an async context manager with trio."""
    with pynng.Pair0(listen=addr + "-dialer-trio") as listener_sock:
        with pynng.Pair0() as dialer_sock:
            dialer = dialer_sock.dial(addr + "-dialer-trio", block=True)
            async with dialer:
                await dialer_sock.asend(b"hello from dialer")
                assert (await listener_sock.arecv()) == b"hello from dialer"
            # after exiting async with, dialer is closed


@pytest.mark.trio
async def test_listener_async_context_manager_trio():
    """Listener can be used as an async context manager with trio."""
    with pynng.Pair0() as sock:
        async with sock.listen(addr + "-listener-trio") as listener:
            assert listener is not None
        # after exiting async with, listener is closed


@pytest.mark.asyncio
async def test_dialer_async_context_manager_asyncio():
    """Dialer can be used as an async context manager with asyncio."""
    with pynng.Pair0(listen=addr + "-dialer-asyncio") as listener_sock:
        with pynng.Pair0() as dialer_sock:
            dialer = dialer_sock.dial(addr + "-dialer-asyncio", block=True)
            async with dialer:
                await dialer_sock.asend(b"hello from dialer")
                assert (await listener_sock.arecv()) == b"hello from dialer"


@pytest.mark.asyncio
async def test_listener_async_context_manager_asyncio():
    """Listener can be used as an async context manager with asyncio."""
    with pynng.Pair0() as sock:
        async with sock.listen(addr + "-listener-asyncio") as listener:
            assert listener is not None


@pytest.mark.trio
async def test_dialer_aclose_trio():
    """Dialer.aclose() works correctly."""
    with pynng.Pair0(listen=addr + "-aclose-trio") as listener_sock:
        with pynng.Pair0() as dialer_sock:
            dialer = dialer_sock.dial(addr + "-aclose-trio", block=True)
            await dialer.aclose()
            # dialer should be closed now


@pytest.mark.asyncio
async def test_listener_aclose_asyncio():
    """Listener.aclose() works correctly."""
    with pynng.Pair0() as sock:
        listener = sock.listen(addr + "-aclose-asyncio")
        await listener.aclose()
