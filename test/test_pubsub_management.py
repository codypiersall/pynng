"""Tests for Sub0 subscription tracking and batch management."""

import platform
import time

import pynng
import pytest

from _test_util import wait_pipe_len
from conftest import random_addr, FAST_TIMEOUT


def test_subscriptions_property_empty():
    """subscriptions property returns empty frozenset on fresh socket."""
    with pynng.Sub0() as sub:
        assert sub.subscriptions == frozenset()


def test_subscriptions_property_tracks_subscribe():
    """subscriptions property reflects topics added via subscribe()."""
    with pynng.Sub0() as sub:
        sub.subscribe(b"topic1")
        sub.subscribe(b"topic2")
        assert sub.subscriptions == frozenset({b"topic1", b"topic2"})


def test_subscriptions_property_tracks_str_topics():
    """String topics are stored as bytes in subscriptions."""
    with pynng.Sub0() as sub:
        sub.subscribe("hello")
        assert sub.subscriptions == frozenset({b"hello"})


def test_subscriptions_property_tracks_constructor_topics():
    """Topics passed via constructor are tracked."""
    with pynng.Sub0(topics=[b"a", b"b", "c"]) as sub:
        assert sub.subscriptions == frozenset({b"a", b"b", b"c"})


def test_subscriptions_property_tracks_constructor_single_str():
    """A single string topic passed via constructor is tracked."""
    with pynng.Sub0(topics="hello") as sub:
        assert sub.subscriptions == frozenset({b"hello"})


def test_subscriptions_property_tracks_constructor_single_bytes():
    """A single bytes topic passed via constructor is tracked."""
    with pynng.Sub0(topics=b"hello") as sub:
        assert sub.subscriptions == frozenset({b"hello"})


def test_subscriptions_returns_frozenset():
    """subscriptions property returns a frozenset (immutable)."""
    with pynng.Sub0(topics=b"x") as sub:
        subs = sub.subscriptions
        assert isinstance(subs, frozenset)
        with pytest.raises(AttributeError):
            subs.add(b"y")


def test_subscribe_idempotent():
    """Subscribing to the same topic twice does not duplicate in tracking set."""
    with pynng.Sub0() as sub:
        sub.subscribe(b"dup")
        sub.subscribe(b"dup")
        assert sub.subscriptions == frozenset({b"dup"})


def test_unsubscribe_removes_from_tracking():
    """unsubscribe removes the topic from the tracking set."""
    with pynng.Sub0(topics=[b"a", b"b"]) as sub:
        sub.unsubscribe(b"a")
        assert sub.subscriptions == frozenset({b"b"})


def test_unsubscribe_nonexistent_topic():
    """Unsubscribing from a topic not subscribed to raises NNGException."""
    with pynng.Sub0() as sub:
        # NNG returns NNG_ENOENT when unsubscribing from a non-subscribed topic.
        with pytest.raises(pynng.NNGException):
            sub.unsubscribe(b"nonexistent")
        assert sub.subscriptions == frozenset()


def test_subscribe_all():
    """subscribe_all subscribes to multiple topics at once."""
    with pynng.Sub0() as sub:
        sub.subscribe_all([b"topic1", b"topic2", "topic3"])
        assert sub.subscriptions == frozenset({b"topic1", b"topic2", b"topic3"})


def test_subscribe_all_empty():
    """subscribe_all with empty iterable is a no-op."""
    with pynng.Sub0() as sub:
        sub.subscribe_all([])
        assert sub.subscriptions == frozenset()


def test_unsubscribe_all():
    """unsubscribe_all clears all subscriptions."""
    with pynng.Sub0(topics=[b"a", b"b", b"c"]) as sub:
        assert len(sub.subscriptions) == 3
        sub.unsubscribe_all()
        assert sub.subscriptions == frozenset()


def test_unsubscribe_all_empty():
    """unsubscribe_all on socket with no subscriptions is a no-op."""
    with pynng.Sub0() as sub:
        sub.unsubscribe_all()
        assert sub.subscriptions == frozenset()


def test_subscribe_unsubscribe_all_cycle():
    """Can subscribe, unsubscribe_all, then subscribe again."""
    with pynng.Sub0() as sub:
        sub.subscribe_all([b"x", b"y"])
        assert len(sub.subscriptions) == 2
        sub.unsubscribe_all()
        assert sub.subscriptions == frozenset()
        sub.subscribe(b"z")
        assert sub.subscriptions == frozenset({b"z"})


@pytest.mark.skipif(
    platform.python_implementation() == "PyPy",
    reason="Sub0 topic filtering has issues on PyPy wheels",
)
def test_topic_filtering_integration():
    """Integration test: only messages matching subscribed topics are received."""
    addr = random_addr()
    with pynng.Pub0(listen=addr) as pub, \
         pynng.Sub0(dial=addr, recv_timeout=FAST_TIMEOUT) as sub:
        wait_pipe_len(pub, 1)

        # Subscribe only to "even:" topics
        sub.subscribe(b"even:")
        time.sleep(0.05)  # brief settle for subscription propagation

        pub.send(b"even:2")
        pub.send(b"odd:1")
        pub.send(b"even:4")

        received = []
        for _ in range(3):
            try:
                msg = sub.recv()
                received.append(msg)
            except pynng.Timeout:
                break

        assert b"even:2" in received
        assert b"even:4" in received
        assert b"odd:1" not in received


@pytest.mark.skipif(
    platform.python_implementation() == "PyPy",
    reason="Sub0 topic filtering has issues on PyPy wheels",
)
def test_unsubscribe_all_stops_receiving():
    """After unsubscribe_all, no more messages are received."""
    addr = random_addr()
    with pynng.Pub0(listen=addr) as pub, \
         pynng.Sub0(dial=addr, recv_timeout=FAST_TIMEOUT) as sub:
        wait_pipe_len(pub, 1)

        sub.subscribe(b"")
        time.sleep(0.05)

        # Verify we can receive
        pub.send(b"hello")
        msg = sub.recv()
        assert msg == b"hello"

        # Unsubscribe from everything
        sub.unsubscribe_all()
        time.sleep(0.05)

        pub.send(b"world")
        with pytest.raises(pynng.Timeout):
            sub.recv()
