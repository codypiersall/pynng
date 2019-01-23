import asyncio
import threading
import time
import itertools

import pytest
import trio
from trio.testing import trio_test

import pynng

addr = 'tcp://127.0.0.1:31245'


def _send_data_bg(sock, sleep_time, data):
    def send():
        time.sleep(sleep_time)
        sock.send(data)
    t = threading.Thread(target=send, daemon=True)
    t.start()
    return t


def test_arecv_asyncio():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with pynng.Pair0(listen=addr, recv_timeout=1000) as listener, \
            pynng.Pair0(dial=addr) as dialer:

        thread = _send_data_bg(dialer, 0.1, b'hello there buddy')
        hey_there = loop.run_until_complete(listener.arecv())
        assert hey_there == b'hello there buddy'
        thread.join()


def test_arecv_asyncio_cancel():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def cancel_soon(fut, sleep_time=0.2):
        await asyncio.sleep(sleep_time)
        fut.cancel()

    with pynng.Pair0(listen=addr, recv_timeout=5000) as p0:
        arecv = p0.arecv()
        fut = asyncio.ensure_future(arecv)
        g = asyncio.gather(fut, cancel_soon(fut))
        with pytest.raises(asyncio.CancelledError):
            loop.run_until_complete(g)


def test_arecv_trio():
    with pynng.Pair0(listen=addr, recv_timeout=1000) as listener, \
            pynng.Pair0(dial=addr) as dialer:

        thread = _send_data_bg(dialer, 0.1, b'hello there buddy')
        hey_there = trio.run(listener.arecv)
        assert hey_there == b'hello there buddy'
        thread.join()


def test_arecv_trio_cancel():
    async def cancel_real_fast(sock):
        with trio.fail_after(0.02):
            return await sock.arecv()

    with pynng.Pair0(listen=addr, recv_timeout=5000) as p0:
        with pytest.raises(trio.TooSlowError):
            trio.run(cancel_real_fast, p0)


def test_asend_asyncio():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with pynng.Pair0(listen=addr, recv_timeout=2000) as listener, \
            pynng.Pair0(dial=addr, send_timeout=2000) as dialer:
        arecv = listener.arecv()
        asend = dialer.asend(b'hello friend')
        g = asyncio.gather(asend, arecv)
        sent, received = loop.run_until_complete(g)
        assert received == b'hello friend'
        assert sent is None


def test_asend_trio():
    async def asend_and_arecv(sender, receiver, msg):
        await sender.asend(msg)
        return await receiver.arecv()

    with pynng.Pair0(listen=addr, recv_timeout=2000) as listener, \
            pynng.Pair0(dial=addr, send_timeout=2000) as dialer:
        msg = trio.run(asend_and_arecv, dialer, listener, b'hello there')
        assert msg == b'hello there'


@trio_test
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
            for i in range(1000):
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

        with pynng.Sub0(dial=addr, recv_timeout=100) as subber:
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

    async with trio.open_nursery() as n:
        # whip up the subs
        for _, lot in itertools.product(range(1), ('even', 'odd')):
            sentinel_received[lot] = False
            n.start_soon(subs, lot)

        # head over to the pub
        await pub()
