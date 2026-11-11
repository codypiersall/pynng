"""Tests for pynng.service.Rep0Service."""

import asyncio
import logging
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
    import gc

    dummy_ctx = object()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", ResourceWarning)
        r = Request(b"test-data", dummy_ctx)
        del r
        gc.collect()
        resource_warnings = [item for item in w if issubclass(item.category, ResourceWarning)]
        assert len(resource_warnings) == 1
        assert str(resource_warnings[0].message) == "Request with data b'test-data' was never replied to"


@pytest.mark.asyncio
async def test_unreplied_request_gc_on_background_thread_wakes_event():
    """Request.__del__ on a background thread safely sets _replied_event via loop.call_soon_threadsafe."""
    import gc
    import threading

    loop = asyncio.get_running_loop()
    replied_event = asyncio.Event()
    holder = [Request(b"bg-data", object(), _replied_event=replied_event, _loop=loop)]

    def drop_in_thread():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            holder.clear()
            gc.collect()

    t = threading.Thread(target=drop_in_thread)
    t.start()
    t.join(timeout=2.0)
    await asyncio.wait_for(replied_event.wait(), timeout=2.0)
    assert replied_event.is_set()


# ---------------------------------------------------------------------------
# Request class unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_data_attribute():
    """Request.data holds the bytes payload."""
    r = Request(b"payload", None)
    assert r.data == b"payload"
    r._replied = True  # suppress warning


@pytest.mark.asyncio
async def test_unreplied_request_unblocks_worker():
    """Dropping a Request object unblocks the worker via __del__ or context manager fallback."""
    addr = _unique_addr("unreplied-unblock")

    async with Rep0Service(addr, workers=1, recv_timeout=3000, send_timeout=3000) as service:
        req = pynng.Req0(dial=addr, recv_timeout=1000, send_timeout=1000)
        wait_pipe_len(req, 1)

        await req.asend(b"req1")
        # Receive req1 and drop it without calling reply()
        async for request in service:
            with request:
                assert request.data == b"req1"
            break

        # In REP/REQ, client req1 will time out because no reply was sent
        with pytest.raises(pynng.Timeout):
            await req.arecv()
        req.close()

        # Now send a second request from a new client to verify the single worker is not deadlocked
        req2 = pynng.Req0(dial=addr, recv_timeout=3000, send_timeout=3000)
        wait_pipe_len(req2, 1)
        await req2.asend(b"req2")

        async for request2 in service:
            assert request2.data == b"req2"
            await request2.reply(b"reply2")
            break

        assert await req2.arecv() == b"reply2"
        req2.close()


@pytest.mark.asyncio
async def test_request_reply_exception_unblocks_worker():
    """If request.reply() encounters an exception, finally ensures worker is unblocked."""
    event = asyncio.Event()
    # Fake context whose asend raises an exception
    class FailingContext:
        async def asend(self, data):
            raise pynng.Closed("Simulated failure", 0)

    r = Request(b"data", FailingContext(), _replied_event=event)
    with pytest.raises(pynng.Closed):
        await r.reply(b"resp")
    # Event must be set even though asend failed
    assert event.is_set()


@pytest.mark.asyncio
async def test_aenter_initialization_failure_cleans_up_socket(monkeypatch):
    """If initialization fails during __aenter__, underlying socket is closed."""
    addr = _unique_addr("init-failure")
    service = Rep0Service(addr, workers=1)

    # Monkeypatch _start_asyncio to simulate an error
    async def mock_start_asyncio():
        raise RuntimeError("Initialization boom")

    monkeypatch.setattr(service, "_start_asyncio", mock_start_asyncio)

    with pytest.raises(RuntimeError, match="Initialization boom"):
        async with service:
            pass

    assert service._socket is None


# ---------------------------------------------------------------------------
# recv_timeout expiry in workers
# ---------------------------------------------------------------------------


def _service_errors(caplog):
    return [
        r
        for r in caplog.records
        if r.name == "pynng.service" and r.levelno >= logging.ERROR
    ]


@pytest.mark.asyncio
async def test_recv_timeout_expiry_logs_no_error_asyncio(caplog):
    """Workers wait through recv_timeout expiries without logging errors."""
    addr = _unique_addr("recv-timeout-quiet-asyncio")
    caplog.set_level(logging.ERROR, logger="pynng.service")

    async with Rep0Service(
        addr, workers=2, recv_timeout=50, send_timeout=1000
    ) as service:
        # Several recv_timeout periods pass with no request.
        await asyncio.sleep(0.3)
        with pynng.Req0(dial=addr, recv_timeout=2000, send_timeout=2000) as req:
            wait_pipe_len(req, 1)
            await req.asend(b"after-timeouts")
            request = await asyncio.wait_for(service.__anext__(), 2)
            assert request.data == b"after-timeouts"
            await request.reply(b"served")
            assert (await req.arecv()) == b"served"

    assert _service_errors(caplog) == []


@pytest.mark.trio
async def test_recv_timeout_expiry_logs_no_error_trio(caplog):
    """Workers wait through recv_timeout expiries without logging errors (trio)."""
    addr = _unique_addr("recv-timeout-quiet-trio")
    caplog.set_level(logging.ERROR, logger="pynng.service")

    async with Rep0Service(
        addr, workers=2, recv_timeout=50, send_timeout=1000
    ) as service:
        await trio.sleep(0.3)
        with pynng.Req0(dial=addr, recv_timeout=2000, send_timeout=2000) as req:
            wait_pipe_len(req, 1)
            await req.asend(b"after-timeouts")
            with trio.fail_after(2):
                request = await service.__anext__()
            assert request.data == b"after-timeouts"
            await request.reply(b"served")
            assert (await req.arecv()) == b"served"

    assert _service_errors(caplog) == []


@pytest.mark.trio
async def test_unreplied_request_cross_thread_gc_trio():
    """Cross-thread GC of an unreplied Request wakes a Trio task waiting on replied_event."""
    import gc
    import threading
    from unittest.mock import MagicMock

    ev = trio.Event()
    ctx = MagicMock()
    req_holder = [Request(b"trio-cross-thread", ctx, _replied_event=ev)]

    def drop_in_thread():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            req_holder.clear()
            gc.collect()
            gc.collect()

    t = threading.Thread(target=drop_in_thread)
    t.start()
    with trio.fail_after(2.0):
        await ev.wait()
    t.join(timeout=2.0)
    assert ev.is_set() is True


@pytest.mark.asyncio
async def test_unreplied_request_cross_thread_gc_standalone_asyncio_event():
    """Cross-thread GC of a Request with standalone asyncio.Event (no explicit _loop) wakes waiter."""
    import gc
    import threading
    from unittest.mock import MagicMock

    ev = asyncio.Event()
    ctx = MagicMock()
    req_holder = [Request(b"asyncio-standalone", ctx, _replied_event=ev)]

    def drop_in_thread():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            req_holder.clear()
            gc.collect()
            gc.collect()

    t = threading.Thread(target=drop_in_thread)
    t.start()
    await asyncio.wait_for(ev.wait(), timeout=2.0)
    t.join(timeout=2.0)
    assert ev.is_set() is True


def test_uninitialized_request_del_no_attribute_error():
    """Request failing in __init__ does not raise AttributeError in __del__."""
    import gc
    import sys

    unraisable_errors = []
    old_hook = sys.unraisablehook
    sys.unraisablehook = lambda args: unraisable_errors.append(args)
    try:
        with pytest.raises(TypeError):
            Request()  # type: ignore[call-arg]
        gc.collect()
    finally:
        sys.unraisablehook = old_hook
    assert unraisable_errors == []


def test_rep0_service_invalid_workers_raises():
    """Rep0Service rejects workers < 1 or boolean workers."""
    with pytest.raises(ValueError, match="workers must be >= 1"):
        Rep0Service("inproc://invalid-workers-0", workers=0)
    with pytest.raises(ValueError, match="workers must be >= 1"):
        Rep0Service("inproc://invalid-workers-neg", workers=-2)
    with pytest.raises(ValueError, match="workers must be >= 1"):
        Rep0Service("inproc://invalid-workers-bool", workers=False)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_rep0_service_early_break_drains_queued_requests_without_warning():
    """Breaking out of Rep0Service when extra requests are queued does not emit ResourceWarning."""
    import gc

    addr = _unique_addr("early-break-drain-asyncio")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", ResourceWarning)
        async with Rep0Service(
            addr, workers=3, recv_timeout=3000, send_timeout=3000
        ) as service:
            c1 = pynng.Req0(dial=addr, recv_timeout=500, send_timeout=1000)
            c2 = pynng.Req0(dial=addr, recv_timeout=500, send_timeout=1000)
            wait_pipe_len(c1, 1)
            wait_pipe_len(c2, 1)
            await c1.asend(b"req-1")
            await c2.asend(b"req-2")
            await asyncio.sleep(0.05)
            async for request in service:
                await request.reply(b"rep-1")
                break
            c1.close()
            c2.close()
        gc.collect()
        resource_warnings = [
            item for item in w if issubclass(item.category, ResourceWarning)
        ]
        assert resource_warnings == []


