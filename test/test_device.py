import asyncio
import threading
import time

import pytest
import pynng
from conftest import random_addr, FAST_TIMEOUT


def test_sync_device_two_sockets():
    front_addr = random_addr()
    back_addr = random_addr()

    rep = pynng.RawRep0(listen=front_addr, recv_timeout=FAST_TIMEOUT)
    req = pynng.RawReq0(listen=back_addr, recv_timeout=FAST_TIMEOUT)

    exc = []

    def run_dev():
        try:
            pynng.device(rep, req)
        except pynng.Closed as e:
            exc.append(e)

    dev_thread = threading.Thread(target=run_dev, daemon=True)
    dev_thread.start()

    time.sleep(0.05)
    with pynng.Req0(dial=front_addr, recv_timeout=FAST_TIMEOUT) as client, pynng.Rep0(
        dial=back_addr, recv_timeout=FAST_TIMEOUT
    ) as worker:
        client.send(b"request-to-device")
        recvd = worker.recv()
        assert recvd == b"request-to-device"

        worker.send(b"reply-from-device")
        reply = client.recv()
        assert reply == b"reply-from-device"

    # Closing socket causes device to exit with Closed
    rep.close()
    dev_thread.join(timeout=1.0)
    assert not dev_thread.is_alive()
    assert len(exc) == 1
    assert isinstance(exc[0], pynng.Closed)

    req.close()


@pytest.mark.asyncio
async def test_adevice_asyncio_forwarding_and_cancel():
    front_addr = random_addr()
    back_addr = random_addr()

    rep = pynng.RawRep0(listen=front_addr, recv_timeout=FAST_TIMEOUT)
    req = pynng.RawReq0(listen=back_addr, recv_timeout=FAST_TIMEOUT)

    dev_task = asyncio.create_task(pynng.adevice(rep, req))
    await asyncio.sleep(0.05)

    with pynng.Req0(dial=front_addr, recv_timeout=FAST_TIMEOUT) as client, pynng.Rep0(
        dial=back_addr, recv_timeout=FAST_TIMEOUT
    ) as worker:
        await client.asend(b"async-ping")
        msg = await worker.arecv()
        assert msg == b"async-ping"

        await worker.asend(b"async-pong")
        reply = await client.arecv()
        assert reply == b"async-pong"

    # Test clean cancellation
    dev_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await dev_task

    rep.close()
    req.close()


@pytest.mark.asyncio
async def test_adevice_asyncio_socket_close():
    front_addr = random_addr()
    back_addr = random_addr()

    rep = pynng.RawRep0(listen=front_addr, recv_timeout=FAST_TIMEOUT)
    req = pynng.RawReq0(listen=back_addr, recv_timeout=FAST_TIMEOUT)

    dev_task = asyncio.create_task(pynng.adevice(rep, req))
    await asyncio.sleep(0.05)

    rep.close()
    with pytest.raises(pynng.Closed):
        await dev_task

    req.close()


@pytest.mark.trio
async def test_adevice_trio_forwarding_and_cancel():
    import trio

    front_addr = random_addr()
    back_addr = random_addr()

    rep = pynng.RawRep0(listen=front_addr, recv_timeout=FAST_TIMEOUT)
    req = pynng.RawReq0(listen=back_addr, recv_timeout=FAST_TIMEOUT)

    async with trio.open_nursery() as nursery:
        nursery.start_soon(pynng.adevice, rep, req)
        await trio.sleep(0.05)

        with pynng.Req0(
            dial=front_addr, recv_timeout=FAST_TIMEOUT
        ) as client, pynng.Rep0(dial=back_addr, recv_timeout=FAST_TIMEOUT) as worker:
            await client.asend(b"trio-ping")
            msg = await worker.arecv()
            assert msg == b"trio-ping"

            await worker.asend(b"trio-pong")
            reply = await client.arecv()
            assert reply == b"trio-pong"

        nursery.cancel_scope.cancel()

    rep.close()
    req.close()
