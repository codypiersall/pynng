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


def test_arecv_trio():
    with pynng.Pair0(listen=addr, recv_timeout=1000) as listener, \
            pynng.Pair0(dial=addr) as dialer:

        thread = _send_data_bg(dialer, 0.1, b'hello there buddy')
        hey_there = trio.run(listener.arecv)
        assert hey_there == b'hello there buddy'
        thread.join()


def test_arecv_trio_cancel_works():
    with pynng.Pair0(listen=addr, recv_timeout=5000) as listener:
        async def cancel_real_fast():
            with trio.fail_after(0.02):
                await listener.arecv()

        with pytest.raises(trio.TooSlowError):
            trio.run(cancel_real_fast)

