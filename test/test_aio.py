import asyncio
import itertools
import time

import pytest
import trio

import pynng

addr = 'inproc://test-addr'


@pytest.mark.trio
async def test_arecv_asend_asyncio():
    with pynng.Pair0(listen=addr, recv_timeout=1000) as listener, \
            pynng.Pair0(dial=addr) as dialer:
        await dialer.asend(b'hello there buddy')
        assert (await listener.arecv()) == b'hello there buddy'


@pytest.mark.asyncio
async def test_arecv_asyncio_cancel():
    async def cancel_soon(fut, sleep_time=0.05):
        # need to sleep for some amount of time to ensure the arecv actually
        # had time to start.
        await asyncio.sleep(sleep_time)
        fut.cancel()

    with pynng.Pair0(listen=addr, recv_timeout=5000) as p0:
        arecv = p0.arecv()
        fut = asyncio.ensure_future(arecv)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.gather(fut, cancel_soon(fut))


@pytest.mark.trio
async def test_asend_trio_send_timeout():
    with pytest.raises(pynng.exceptions.Timeout):
        with pynng.Pair0(listen=addr, send_timeout=1) as p0:
            await p0.asend(b'foo')


@pytest.mark.asyncio
async def test_asend_asyncio_send_timeout():
    with pytest.raises(pynng.exceptions.Timeout):
        with pynng.Pair0(listen=addr, send_timeout=1) as p0:
            await p0.asend(b'foo')


@pytest.mark.trio
async def test_arecv_trio_cancel():
    with pynng.Pair0(listen=addr, recv_timeout=5000) as p0:
        with pytest.raises(trio.TooSlowError):
            with trio.fail_after(0.001):
                await p0.arecv()


@pytest.mark.trio
async def test_asend_arecv_trio():
    with pynng.Pair0(listen=addr, recv_timeout=2000) as listener, \
            pynng.Pair0(dial=addr, send_timeout=2000) as dialer:
        await dialer.asend(b'hello there')
        assert (await listener.arecv()) == b'hello there'


@pytest.mark.trio
async def test_pub_sub_trio():
    """Demonstrate pub-sub protocol use with ``trio``.

    Start a publisher which publishes 1000 integers and marks each value
    as *even* or *odd* (its parity). Spawn 4 subscribers (2 for consuming
    the evens and 2 for consuming the odds) in separate tasks and have each
    one retreive values and verify the parity.
    """
    sentinel_received = {}

    def is_even(i):
        return i % 2 == 0

    async def pub():
        with pynng.Pub0(listen=addr) as pubber:
            for i in range(20):
                prefix = 'even' if is_even(i) else 'odd'
                msg = '{}:{}'.format(prefix, i)
                await pubber.asend(msg.encode('ascii'))

            while not all(sentinel_received.values()):
                # signal completion
                await pubber.asend(b'odd:None')
                await pubber.asend(b'even:None')

    async def subs(which):
        if which == 'even':
            pred = is_even
        else:
            pred = lambda i: not is_even(i)

        with pynng.Sub0(dial=addr, recv_timeout=5000) as subber:
            subber.subscribe(which + ':')

            while True:
                val = await subber.arecv()
                print(val)

                lot, _, i = val.partition(b':')

                if i == b'None':
                    break

                assert pred(int(i))

            # mark subscriber as having received None sentinel
            sentinel_received[which] = True
            # TODO: This sleep is a hack.
            time.sleep(0.05)

    async with trio.open_nursery() as n:
        # whip up the subs
        for _, lot in itertools.product(range(1), ('even', 'odd')):
            sentinel_received[lot] = False
            n.start_soon(subs, lot)

        # head over to the pub
        await pub()
