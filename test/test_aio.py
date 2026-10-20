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
