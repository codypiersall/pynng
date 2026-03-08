"""Tests for async pipe event streams."""

import asyncio

import pytest

import pynng
from pynng import PipeEvent, PipeEventStream


@pytest.mark.asyncio
async def test_pipe_events_post_add_on_connect():
    """Connecting a dialer produces a post_add event on the listener."""
    addr = "inproc://test-pipe-events-post-add"
    with pynng.Pair0(listen=addr) as s0:
        stream = s0.pipe_events()
        try:
            with pynng.Pair0(dial=addr) as s1:
                event = await asyncio.wait_for(stream.__anext__(), timeout=5)
                # We may get pre_add first; collect until we see post_add
                events = [event]
                while not any(e.event_type == "post_add" for e in events):
                    event = await asyncio.wait_for(stream.__anext__(), timeout=5)
                    events.append(event)

                post_add_events = [e for e in events if e.event_type == "post_add"]
                assert len(post_add_events) >= 1
                assert isinstance(post_add_events[0], PipeEvent)
                assert isinstance(post_add_events[0].pipe, pynng.Pipe)
        finally:
            stream.close()


@pytest.mark.asyncio
async def test_pipe_events_remove_on_disconnect():
    """Closing a dialer socket produces a remove event on the listener."""
    addr = "inproc://test-pipe-events-remove"
    with pynng.Pair0(listen=addr) as s0:
        stream = s0.pipe_events()
        try:
            s1 = pynng.Pair0(dial=addr)
            # Wait for post_add
            events = []
            while not any(e.event_type == "post_add" for e in events):
                event = await asyncio.wait_for(stream.__anext__(), timeout=5)
                events.append(event)

            # Close dialer to trigger remove
            s1.close()

            # Collect until we see remove
            while not any(e.event_type == "remove" for e in events):
                event = await asyncio.wait_for(stream.__anext__(), timeout=5)
                events.append(event)

            remove_events = [e for e in events if e.event_type == "remove"]
            assert len(remove_events) >= 1
            assert isinstance(remove_events[0].pipe, pynng.Pipe)
        finally:
            stream.close()


@pytest.mark.asyncio
async def test_pipe_events_pre_add():
    """Connecting produces pre_add events."""
    addr = "inproc://test-pipe-events-pre-add"
    with pynng.Pair0(listen=addr) as s0:
        stream = s0.pipe_events()
        try:
            with pynng.Pair0(dial=addr) as s1:
                event = await asyncio.wait_for(stream.__anext__(), timeout=5)
                # The very first event should be pre_add
                assert event.event_type == "pre_add"
                assert isinstance(event.pipe, pynng.Pipe)
        finally:
            stream.close()


@pytest.mark.asyncio
async def test_pipe_events_all_three_types():
    """A connect/disconnect cycle produces pre_add, post_add, and remove."""
    addr = "inproc://test-pipe-events-all-three"
    with pynng.Pair0(listen=addr) as s0:
        stream = s0.pipe_events()
        try:
            s1 = pynng.Pair0(dial=addr)

            # Collect pre_add and post_add
            events = []
            while not any(e.event_type == "post_add" for e in events):
                event = await asyncio.wait_for(stream.__anext__(), timeout=5)
                events.append(event)

            # Close dialer to trigger remove
            s1.close()

            while not any(e.event_type == "remove" for e in events):
                event = await asyncio.wait_for(stream.__anext__(), timeout=5)
                events.append(event)

            event_types = {e.event_type for e in events}
            assert "pre_add" in event_types
            assert "post_add" in event_types
            assert "remove" in event_types
        finally:
            stream.close()


@pytest.mark.asyncio
async def test_pipe_events_close_unregisters_callbacks():
    """Closing the stream unregisters callbacks from the socket."""
    addr = "inproc://test-pipe-events-close"
    with pynng.Pair0(listen=addr) as s0:
        pre_count_before = len(s0._on_pre_pipe_add)
        post_count_before = len(s0._on_post_pipe_add)
        remove_count_before = len(s0._on_post_pipe_remove)

        stream = s0.pipe_events()

        assert len(s0._on_pre_pipe_add) == pre_count_before + 1
        assert len(s0._on_post_pipe_add) == post_count_before + 1
        assert len(s0._on_post_pipe_remove) == remove_count_before + 1

        stream.close()

        assert len(s0._on_pre_pipe_add) == pre_count_before
        assert len(s0._on_post_pipe_add) == post_count_before
        assert len(s0._on_post_pipe_remove) == remove_count_before


@pytest.mark.asyncio
async def test_pipe_events_async_context_manager():
    """PipeEventStream works as an async context manager."""
    addr = "inproc://test-pipe-events-ctx-mgr"
    with pynng.Pair0(listen=addr) as s0:
        async with s0.pipe_events() as stream:
            assert isinstance(stream, PipeEventStream)
            with pynng.Pair0(dial=addr) as s1:
                event = await asyncio.wait_for(stream.__anext__(), timeout=5)
                assert event.event_type in ("pre_add", "post_add", "remove")

        # After exiting async with, callbacks should be unregistered
        assert stream._closed


@pytest.mark.asyncio
async def test_pipe_events_close_is_idempotent():
    """Calling close() multiple times does not raise."""
    addr = "inproc://test-pipe-events-idempotent"
    with pynng.Pair0(listen=addr) as s0:
        stream = s0.pipe_events()
        stream.close()
        stream.close()  # Should not raise


@pytest.mark.asyncio
async def test_pipe_events_stops_after_close():
    """After close(), the async iterator raises StopAsyncIteration."""
    addr = "inproc://test-pipe-events-stop"
    with pynng.Pair0(listen=addr) as s0:
        stream = s0.pipe_events()
        stream.close()
        with pytest.raises(StopAsyncIteration):
            await stream.__anext__()


@pytest.mark.asyncio
async def test_pipe_events_multiple_streams():
    """Multiple streams on the same socket each receive events."""
    addr = "inproc://test-pipe-events-multi"
    with pynng.Pair0(listen=addr) as s0:
        stream1 = s0.pipe_events()
        stream2 = s0.pipe_events()
        try:
            with pynng.Pair0(dial=addr) as s1:
                event1 = await asyncio.wait_for(stream1.__anext__(), timeout=5)
                event2 = await asyncio.wait_for(stream2.__anext__(), timeout=5)
                assert event1.event_type == event2.event_type
        finally:
            stream1.close()
            stream2.close()
