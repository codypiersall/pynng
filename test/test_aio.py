import asyncio
import threading
import time

import pytest
import trio

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
