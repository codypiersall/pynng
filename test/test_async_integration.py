"""Async integration tests for multi-peer messaging topologies.

Tests that NNG messaging patterns work correctly under Python's async
event loops (trio), exercising concurrent callback delivery, context
multiplexing, and socket lifecycle management through the CFFI wrapper
layer.
"""

import pytest
import trio

import pynng
from _test_util import wait_pipe_len
from conftest import random_addr, FAST_TIMEOUT, MEDIUM_TIMEOUT, SLOW_TIMEOUT


# ---------------------------------------------------------------------------
# 1. Fan-out/Fan-in: Pub/Sub with multiple subscribers
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_pubsub_fanout_all_subscribers_receive_trio():
    """1 publisher, 3 subscribers all subscribed to everything.

    All subscribers must receive all N messages.  This exercises concurrent
    callback delivery under the GIL with trio.
    """
    addr = random_addr()
    num_messages = 20
    num_subs = 3

    with pynng.Pub0(listen=addr) as pub:
        subs = []
        for _ in range(num_subs):
            s = pynng.Sub0(dial=addr, recv_timeout=MEDIUM_TIMEOUT)
            s.subscribe(b"")
            subs.append(s)

        # Wait for all pipes to connect
        wait_pipe_len(pub, num_subs)
        for s in subs:
            wait_pipe_len(s, 1)

        received = [[] for _ in range(num_subs)]
        ready_events = [trio.Event() for _ in range(num_subs)]

        async def recv_all(idx, sub):
            ready_events[idx].set()
            for _ in range(num_messages):
                msg = await sub.arecv()
                received[idx].append(msg)

        async def sender():
            for ev in ready_events:
                await ev.wait()
            # Give subscribers a checkpoint to reach arecv()
            await trio.lowlevel.checkpoint()
            for i in range(num_messages):
                await pub.asend(f"msg:{i}".encode())

        async with trio.open_nursery() as nursery:
            for idx, sub in enumerate(subs):
                nursery.start_soon(recv_all, idx, sub)
            nursery.start_soon(sender)

        for sub in subs:
            sub.close()

    # Verify all subscribers received all messages
    for idx in range(num_subs):
        expected = sorted(f"msg:{i}".encode() for i in range(num_messages))
        assert sorted(received[idx]) == expected, (
            f"Subscriber {idx} received wrong messages: {received[idx]}"
        )


@pytest.mark.trio
async def test_pubsub_topic_filtering_trio():
    """Subscribers with different topic filters only receive matching messages."""
    addr = random_addr()
    num_per_topic = 10

    with pynng.Pub0(listen=addr) as pub:
        sub_even = pynng.Sub0(dial=addr, recv_timeout=MEDIUM_TIMEOUT)
        sub_even.subscribe(b"even:")
        sub_odd = pynng.Sub0(dial=addr, recv_timeout=MEDIUM_TIMEOUT)
        sub_odd.subscribe(b"odd:")

        wait_pipe_len(pub, 2)
        wait_pipe_len(sub_even, 1)
        wait_pipe_len(sub_odd, 1)

        received_even = []
        received_odd = []
        ready_even = trio.Event()
        ready_odd = trio.Event()

        async def recv_even():
            ready_even.set()
            for _ in range(num_per_topic):
                msg = await sub_even.arecv()
                received_even.append(msg)

        async def recv_odd():
            ready_odd.set()
            for _ in range(num_per_topic):
                msg = await sub_odd.arecv()
                received_odd.append(msg)

        async def sender():
            await ready_even.wait()
            await ready_odd.wait()
            await trio.lowlevel.checkpoint()
            for i in range(num_per_topic * 2):
                prefix = b"even:" if i % 2 == 0 else b"odd:"
                await pub.asend(prefix + str(i).encode())

        async with trio.open_nursery() as nursery:
            nursery.start_soon(recv_even)
            nursery.start_soon(recv_odd)
            nursery.start_soon(sender)

        sub_even.close()
        sub_odd.close()

    expected_even = sorted(b"even:" + str(i).encode() for i in range(0, num_per_topic * 2, 2))
    expected_odd = sorted(b"odd:" + str(i).encode() for i in range(1, num_per_topic * 2, 2))
    assert sorted(received_even) == expected_even, f"Even messages wrong: {received_even}"
    assert sorted(received_odd) == expected_odd, f"Odd messages wrong: {received_odd}"



# ---------------------------------------------------------------------------
# 3. Pipeline fan-out: Push/Pull distribution
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_push_pull_fanout_trio():
    """1 Push, 3+ Pulls. All messages distributed (not duplicated) across pullers.

    Total received across all pullers must equal total sent.
    """
    addr = random_addr()
    num_messages = 30
    num_pullers = 3

    with pynng.Push0(
        listen=addr, send_timeout=SLOW_TIMEOUT, send_buffer_size=64
    ) as push:
        pullers = []
        for _ in range(num_pullers):
            p = pynng.Pull0(dial=addr, recv_timeout=MEDIUM_TIMEOUT, recv_buffer_size=64)
            pullers.append(p)

        wait_pipe_len(push, num_pullers)
        for p in pullers:
            wait_pipe_len(p, 1)

        received = [[] for _ in range(num_pullers)]
        all_sent = set()
        all_received_event = trio.Event()

        async def recv_loop(idx, puller):
            while True:
                try:
                    msg = await puller.arecv()
                    received[idx].append(msg)
                    if sum(len(r) for r in received) == num_messages:
                        all_received_event.set()
                except (pynng.Timeout, pynng.Closed):
                    break

        async def send_loop():
            for i in range(num_messages):
                data = f"push-{i}".encode()
                all_sent.add(data)
                await push.asend(data)

        async with trio.open_nursery() as nursery:
            for idx, puller in enumerate(pullers):
                nursery.start_soon(recv_loop, idx, puller)
            nursery.start_soon(send_loop)
            await all_received_event.wait()
            # Once all messages arrived, close pullers to exit recv_loop immediately
            for p in pullers:
                p.close()


    # Total received == total sent (no duplication, no loss)
    all_received = []
    for r in received:
        all_received.extend(r)
    assert len(all_received) == num_messages, (
        f"Received {len(all_received)} messages, expected {num_messages}"
    )
    assert set(all_received) == all_sent

    # Verify distribution: each puller got at least 1 message
    for idx in range(num_pullers):
        assert len(received[idx]) > 0, (
            f"Puller {idx} received no messages"
        )


# ---------------------------------------------------------------------------
# 4. Pair1 polyamorous routing
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_pair1_polyamorous_routing_trio():
    """Pair1 listener with polyamorous=True routes messages to specific peers via pipes."""
    addr = random_addr()
    num_dialers = 3

    with pynng.Pair1(
        listen=addr, polyamorous=True, recv_timeout=MEDIUM_TIMEOUT
    ) as listener:
        dialers = []
        for _ in range(num_dialers):
            d = pynng.Pair1(
                dial=addr, polyamorous=True, recv_timeout=MEDIUM_TIMEOUT
            )
            dialers.append(d)

        wait_pipe_len(listener, num_dialers)
        for d in dialers:
            wait_pipe_len(d, 1)

        # Each dialer sends an identifying message
        for idx, d in enumerate(dialers):
            await d.asend(f"hello-from-{idx}".encode())

        # Listener receives all messages and tracks which pipe each came from
        pipe_to_dialer_idx = {}
        for _ in range(num_dialers):
            msg = await listener.arecv_msg()
            data = msg.bytes
            # Parse "hello-from-N"
            dialer_idx = int(data.split(b"-")[-1])
            pipe_to_dialer_idx[msg.pipe.id] = dialer_idx

        assert len(pipe_to_dialer_idx) == num_dialers

        # Now send targeted replies via each pipe
        for pipe in listener.pipes:
            dialer_idx = pipe_to_dialer_idx[pipe.id]
            await pipe.asend(
                f"reply-to-{dialer_idx}".encode()
            )

        # Each dialer should get only its own reply
        for idx, d in enumerate(dialers):
            reply = await d.arecv()
            assert reply == f"reply-to-{idx}".encode(), (
                f"Dialer {idx} got wrong reply: {reply}"
            )

        for d in dialers:
            d.close()


# ---------------------------------------------------------------------------
# 5. Survey pattern with timeout
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_survey_with_partial_responses_trio():
    """Surveyor sends survey; some respondents reply, some don't.

    Verify surveyor collects available responses within timeout and
    does not hang or deadlock.
    """
    addr = random_addr()

    with pynng.Surveyor0(
        listen=addr, recv_timeout=MEDIUM_TIMEOUT, survey_time=FAST_TIMEOUT
    ) as surveyor:
        respondents = []
        for _ in range(3):
            r = pynng.Respondent0(dial=addr, recv_timeout=MEDIUM_TIMEOUT)
            respondents.append(r)

        wait_pipe_len(surveyor, 3)
        for r in respondents:
            wait_pipe_len(r, 1)

        responses_collected = []

        async def respond(idx, respondent):
            question = await respondent.arecv()
            assert question == b"survey-question"
            if idx < 2:
                # First two respondents reply immediately
                await respondent.asend(
                    f"response-{idx}".encode()
                )
            # Third respondent does not reply (simulating slow/absent)

        async def collect_responses():
            await surveyor.asend(b"survey-question")
            # Collect responses until survey_time expires
            while True:
                try:
                    resp = await surveyor.arecv()
                    responses_collected.append(resp)
                except pynng.Timeout:
                    break

        async with trio.open_nursery() as nursery:
            for idx, r in enumerate(respondents):
                nursery.start_soon(respond, idx, r)
            nursery.start_soon(collect_responses)

        for r in respondents:
            r.close()

    # Should have exactly 2 responses (from respondents 0 and 1)
    assert sorted(responses_collected) == [b"response-0", b"response-1"], (
        f"Unexpected survey responses: {responses_collected}"
    )


# ---------------------------------------------------------------------------
# 7. Rapid open/close under async load
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_rapid_open_close_trio():
    """Open socket, start async recv, close quickly. Repeat 10+ times.

    Verify no segfault, no hang, proper Closed exception each time.
    """
    for i in range(15):
        addr = random_addr()
        sock = pynng.Pair0(listen=addr, recv_timeout=SLOW_TIMEOUT)

        async with trio.open_nursery() as nursery:
            got_closed = False

            async def try_recv():
                nonlocal got_closed
                try:
                    await sock.arecv()
                except pynng.Closed:
                    got_closed = True

            async def close_soon():
                await trio.lowlevel.checkpoint()
                sock.close()

            nursery.start_soon(try_recv)
            nursery.start_soon(close_soon)

        assert got_closed, f"Iteration {i} did not get Closed"


@pytest.mark.trio
async def test_rapid_open_close_with_connected_peer_trio():
    """Open socket, connect peer, start async recv, close quickly.

    Tests that closing a connected socket under active async recv does not
    segfault or hang, even with an active peer.
    """
    for i in range(10):
        addr = random_addr()
        listener = pynng.Pair0(listen=addr, recv_timeout=SLOW_TIMEOUT)
        dialer = pynng.Pair0(dial=addr, recv_timeout=SLOW_TIMEOUT)
        wait_pipe_len(listener, 1)

        async with trio.open_nursery() as nursery:
            got_exception = False

            async def try_recv():
                nonlocal got_exception
                try:
                    await listener.arecv()
                except pynng.Closed:
                    got_exception = True

            async def close_soon():
                await trio.lowlevel.checkpoint()
                listener.close()


            nursery.start_soon(try_recv)
            nursery.start_soon(close_soon)

        dialer.close()
        assert got_exception


# ---------------------------------------------------------------------------
# 8. Mixed sync/async on same socket
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_mixed_sync_async_trio():
    """Alternate between sync and async operations on the same socket pair."""
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=MEDIUM_TIMEOUT, send_timeout=MEDIUM_TIMEOUT) as s0, \
         pynng.Pair0(dial=addr, recv_timeout=MEDIUM_TIMEOUT, send_timeout=MEDIUM_TIMEOUT) as s1:
        wait_pipe_len(s0, 1)

        for i in range(5):
            if i % 2 == 0:
                # Sync send from s0
                s0.send(f"sync-{i}".encode())
                result = await s1.arecv()
            else:
                # Async send from s0
                await s0.asend(f"async-{i}".encode())
                result = s1.recv()

            if i % 2 == 0:
                assert result == f"sync-{i}".encode()
            else:
                assert result == f"async-{i}".encode()


# ---------------------------------------------------------------------------
# 10. Double-close safety
# ---------------------------------------------------------------------------

def test_double_close_socket_is_safe():
    """Verify closing a socket twice does not raise."""
    addr = random_addr()
    s = pynng.Pair0(listen=addr)
    s.close()
    s.close()  # Should not raise


# ---------------------------------------------------------------------------
# 12. Zero-length message
# ---------------------------------------------------------------------------

@pytest.mark.trio
async def test_send_recv_empty_message_trio():
    """Verify empty messages can be sent and received."""
    addr = random_addr()
    with pynng.Pair0(listen=addr, recv_timeout=MEDIUM_TIMEOUT) as s0:
        with pynng.Pair0(dial=addr, send_timeout=MEDIUM_TIMEOUT) as s1:
            wait_pipe_len(s0, 1)
            await s1.asend(b"")
            result = await s0.arecv()
            assert result == b""
