import asyncio
import itertools

import pytest
import trio

import pynng

from conftest import random_addr, FAST_TIMEOUT, MEDIUM_TIMEOUT, SLOW_TIMEOUT


@pytest.mark.asyncio
async def test_arecv_asend_asyncio():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as listener, pynng.Pair0(
        dial=addr
    ) as dialer:
        await dialer.asend(b"hello there buddy")
        assert (await listener.arecv()) == b"hello there buddy"


@pytest.mark.trio
async def test_asend_arecv_trio():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=MEDIUM_TIMEOUT) as listener, pynng.Pair0(
        dial=addr, send_timeout=MEDIUM_TIMEOUT
    ) as dialer:
        await dialer.asend(b"hello there")
        assert (await listener.arecv()) == b"hello there"


@pytest.mark.trio
async def test_arecv_trio_cancel():
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=SLOW_TIMEOUT) as p0:
        with pytest.raises(trio.TooSlowError):
            with trio.fail_after(0.001):
                await p0.arecv()


@pytest.mark.asyncio
async def test_arecv_asyncio_cancel():
    async def cancel_soon(fut, sleep_time=0.05):
        # need to sleep for some amount of time to ensure the arecv actually
        # had time to start.
        await asyncio.sleep(sleep_time)
        fut.cancel()

    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=SLOW_TIMEOUT) as p0:
        arecv = p0.arecv()
        fut = asyncio.ensure_future(arecv)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.gather(fut, cancel_soon(fut))


@pytest.mark.asyncio
async def test_arecv_cancellation():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s1:
        task = asyncio.create_task(s1.arecv())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_arecv_cancellation_immediate():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s1:
        task = asyncio.create_task(s1.arecv())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_arecv_cancellation_race_with_send():
    addr = random_addr()
    with pynng.Pair0(listen=addr) as s1, pynng.Pair0(dial=addr) as s2:
        task = asyncio.create_task(s1.arecv())
        # Cancel the task while simultaneously sending a message to simulate race
        task.cancel()
        s2.send(b"racing message")
        with pytest.raises(asyncio.CancelledError):
            await task
        # The racing message remains queued in the socket and can be cleanly received
        assert (await s1.arecv()) == b"racing message"
        await s2.asend(b"subsequent message")
        assert (await s1.arecv()) == b"subsequent message"


@pytest.mark.asyncio
async def test_asend_asyncio_send_timeout():
    addr = random_addr()
    with pytest.raises(pynng.exceptions.Timeout):
        with pynng.Pair0(listen=addr, send_timeout=1) as p0:
            await p0.asend(b"foo")


@pytest.mark.trio
async def test_asend_trio_send_timeout():
    addr = random_addr()
    with pytest.raises(pynng.exceptions.Timeout):
        with pynng.Pair0(listen=addr, send_timeout=1) as p0:
            await p0.asend(b"foo")


@pytest.mark.trio
async def test_pub_sub_trio():
    """Demonstrate pub-sub protocol use with ``trio``.

    Start a publisher which publishes 20 integers and marks each value
    as *even* or *odd* (its parity). Spawn 2 subscribers (1 for consuming
    the evens and 1 for consuming the odds) in separate tasks and have each
    one retrieve values and verify the parity.
    """
    addr = random_addr()
    sentinel_received = {}

    def is_even(i):
        return i % 2 == 0

    async def pub():
        with pynng.Pub0(listen=addr) as pubber:
            # Wait until both subscribers have connected before publishing.
            # inproc is reliable but messages sent before subscription is
            # established are dropped.
            while len(pubber.pipes) < 2:
                await trio.sleep(0.01)

            for i in range(20):
                prefix = "even" if is_even(i) else "odd"
                msg = f"{prefix}:{i}"
                await pubber.asend(msg.encode("ascii"))

            while not all(sentinel_received.values()):
                # signal completion
                await pubber.asend(b"odd:None")
                await pubber.asend(b"even:None")

    async def subs(which):
        if which == "even":
            expected_values = list(range(0, 20, 2))  # [0, 2, 4, ..., 18]
        else:
            expected_values = list(range(1, 20, 2))  # [1, 3, 5, ..., 19]

        with pynng.Sub0(dial=addr, recv_timeout=SLOW_TIMEOUT) as subber:
            subber.subscribe(which + ":")

            received_values = []
            while True:
                val = await subber.arecv()

                lot, _, i = val.partition(b":")

                if i == b"None":
                    break

                received_values.append(int(i))

            # The publisher sends 20 messages (10 per parity). Since pub
            # waits for both subscribers to connect before publishing,
            # all 10 messages must arrive with exactly the right values.
            assert sorted(received_values) == expected_values, (
                f"{which} subscriber received wrong values: {sorted(received_values)!r}, "
                f"expected {expected_values!r}"
            )
            # mark subscriber as having received None sentinel
            sentinel_received[which] = True

    async with trio.open_nursery() as n:
        # whip up the subs
        for _, lot in itertools.product(range(1), ("even", "odd")):
            sentinel_received[lot] = False
            n.start_soon(subs, lot)

        # head over to the pub
        await pub()


@pytest.mark.asyncio
async def test_aio_free_cancels_pending():
    from pynng._aio import AIOHelper, _aio_map, _aio_map_lock

    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0:
        # 1. Default MPSC engine path under asyncio: zero _aio_map registration
        mpsc_helper = AIOHelper(s0, "asyncio")
        assert mpsc_helper._mpsc_engine is not None
        assert mpsc_helper._aio_entry is not None
        assert mpsc_helper.cb_arg is None
        mpsc_helper._free()
        assert mpsc_helper.aio is None
        assert mpsc_helper._aio_entry is None

        # 2. Fallback _aio_map callback path (_use_mpsc=False)
        helper = AIOHelper(s0, "asyncio", _use_mpsc=False)
        cb_id = id(helper.cb_arg)
        with _aio_map_lock:
            assert cb_id in _aio_map
        # Explicit _free should cancel pending AIO and pop cb_arg
        helper._free()
        assert helper.aio is None
        with _aio_map_lock:
            assert cb_id not in _aio_map
        if helper.awaitable is not None:
            helper.awaitable.close()


@pytest.mark.asyncio
async def test_aio_free_cleans_map_when_aio_is_none():
    from pynng._aio import AIOHelper, _aio_map, _aio_map_lock, lib

    addr = random_addr()
    with pynng.Pair0(listen=addr) as s0:
        helper = AIOHelper(s0, "asyncio", _use_mpsc=False)
        cb_id = id(helper.cb_arg)
        with _aio_map_lock:
            assert cb_id in _aio_map
        # Simulate helper whose aio was freed or failed to allocate
        lib.nng_aio_free(helper.aio)
        helper.aio = None
        helper._free()
        with _aio_map_lock:
            assert cb_id not in _aio_map
        if helper.awaitable is not None:
            helper.awaitable.close()


def test_aio_map_multithreaded_access():
    import concurrent.futures
    from pynng._aio import _aio_map, _aio_map_lock, _async_complete
    from pynng._nng import ffi

    def churn_map(idx):
        obj = object()
        obj_id = id(obj)
        with _aio_map_lock:
            _aio_map[obj_id] = lambda: None
        # Call completion
        void_p = ffi.cast("void *", obj_id)
        _async_complete(void_p)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(churn_map, i) for i in range(100)]
        for f in futures:
            f.result()


def test_mpsc_deferred_free_when_queued_prevents_uaf_and_cycle():
    """Verify freeing an entry while queued in C11 MPSC defers free until pop and prevents self-cycles."""
    from pynng._nng import ffi, lib

    q = lib.pynng_mpsc_queue_new(-1)
    try:
        e1 = lib.pynng_aio_entry_new(ffi.NULL, 101, q)
        assert lib.pynng_aio_entry_is_idle(e1) == 1

        # Push e1 into the MPSC queue
        lib.pynng_native_aio_complete(e1)
        assert lib.pynng_aio_entry_is_idle(e1) == 0

        # Calling pynng_native_aio_complete a second time while queued must be a no-op (no self-cycle)
        lib.pynng_native_aio_complete(e1)

        # Free e1 before the consumer drains the queue (simulates _free() right after nng_aio_cancel)
        lib.pynng_aio_entry_free(e1)

        # Allocate and push a second entry e2
        e2 = lib.pynng_aio_entry_new(ffi.NULL, 202, q)
        lib.pynng_native_aio_complete(e2)

        # Drain batch: e1 was freed so its slot is skipped and reclaimed; only e2 (202) is returned
        out = ffi.new("uintptr_t[16]")
        count = lib.pynng_mpsc_drain_batch(q, out, 16)
        assert [out[i] for i in range(count)] == [202]
        assert lib.pynng_aio_entry_is_idle(e2) == 1

        lib.pynng_aio_entry_free(e2)
    finally:
        lib.pynng_mpsc_queue_free(q)


@pytest.mark.asyncio
async def test_mpsc_batch_drain_over_256():
    """Verify MPSCAIOEngine drains more than _batch_size (256) completions in a single notification."""
    from pynng._aio import MPSCAIOEngine
    from pynng._nng import ffi, lib

    loop = asyncio.get_running_loop()
    engine = MPSCAIOEngine.get_for_loop(loop, lib, ffi)
    assert engine is not None

    entries = []
    futs = []
    try:
        for _ in range(300):
            fut = loop.create_future()
            slot = engine.register(fut)
            entry = lib.pynng_aio_entry_new(ffi.NULL, slot, engine._queue)
            entries.append(entry)
            futs.append(fut)
            lib.pynng_native_aio_complete(entry)

        await asyncio.wait_for(asyncio.gather(*futs), timeout=2.0)
        assert all(f.done() for f in futs)
        assert len(engine._slots) == 0
    finally:
        for entry in entries:
            lib.pynng_aio_entry_free(entry)


@pytest.mark.asyncio
async def test_pooled_asend_timeout_and_cancel_do_not_leak_nng_msg():
    """Verify failed/timed-out/cancelled pooled asend detaches and frees the unsent nng_msg."""
    addr = random_addr()
    with pynng.Req0(send_timeout=20) as req:
        with pytest.raises(pynng.Timeout):
            await req.asend(b"timeout-payload")

        assert len(req._send_pool) == 1
        helper = req._send_pool[0]
        assert req._lib.nng_aio_get_msg(helper.aio) == req._ffi.NULL

        msg = pynng.Message(b"timeout-msg-payload")
        with pytest.raises(pynng.Timeout):
            await req.asend_msg(msg)

        assert len(req._send_pool) == 1
        assert req._lib.nng_aio_get_msg(req._send_pool[0].aio) == req._ffi.NULL

        # Verify pooled helper still works once connected
        with pynng.Rep0(listen=addr) as rep:
            req.dial(addr, block=True)
            await req.asend(b"after-timeout")
            assert (await rep.arecv()) == b"after-timeout"


def test_socket_and_context_reuse_across_event_loops():
    """Verify reusing a Socket and Context across multiple asyncio.run() loops works without leaking FDs."""
    addr = random_addr()
    with pynng.Rep0(listen=addr) as rep, pynng.Req0(dial=addr) as req:
        ctx_rep = rep.new_context()
        ctx_req = req.new_context()
        try:
            for i in range(4):
                payload = f"loop-{i}".encode()

                async def roundtrip():
                    await req.asend(payload)
                    assert (await rep.arecv()) == payload
                    await rep.asend(payload + b"-reply")
                    assert (await req.arecv()) == payload + b"-reply"

                    await ctx_req.asend(payload + b"-ctx")
                    assert (await ctx_rep.arecv()) == payload + b"-ctx"
                    await ctx_rep.asend(payload + b"-ctx-reply")
                    assert (await ctx_req.arecv()) == payload + b"-ctx-reply"

                asyncio.run(roundtrip())
        finally:
            ctx_rep.close()
            ctx_req.close()


@pytest.mark.asyncio
async def test_device_aio_cancellation_with_mpsc():
    """Verify cancelling DeviceAIO.run() under MPSC engine raises CancelledError cleanly without UAF."""
    from pynng._aio import DeviceAIO

    a1 = random_addr()
    a2 = random_addr()
    with pynng.RawPair0(listen=a1) as s1, pynng.RawPair0(listen=a2) as s2:
        dev = DeviceAIO(s1, s2, "asyncio")
        assert dev._mpsc_engine is not None
        task = asyncio.create_task(dev.run())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert dev.aio is None
        assert dev._aio_entry is None

