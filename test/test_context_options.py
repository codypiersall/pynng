"""Tests for per-context option descriptors (recv_timeout, send_timeout)."""

import pynng
import pytest

addr = "inproc://test-context-options"


def test_context_recv_timeout_get_set():
    """recv_timeout can be get/set on a context independently of the socket."""
    with pynng.Rep0(listen=addr) as s:
        ctx = s.new_context()
        try:
            # default is -1 (infinite)
            assert ctx.recv_timeout == -1
            ctx.recv_timeout = 100
            assert ctx.recv_timeout == 100
            # socket timeout should still be default
            assert s.recv_timeout == -1
        finally:
            ctx.close()


def test_context_send_timeout_get_set():
    """send_timeout can be get/set on a context independently of the socket."""
    with pynng.Rep0(listen=addr + "-send") as s:
        ctx = s.new_context()
        try:
            assert ctx.send_timeout == -1
            ctx.send_timeout = 200
            assert ctx.send_timeout == 200
            assert s.send_timeout == -1
        finally:
            ctx.close()


def test_two_contexts_independent_timeouts():
    """Two contexts on the same socket can have different timeouts."""
    with pynng.Rep0(listen=addr + "-independent") as s:
        ctx1 = s.new_context()
        ctx2 = s.new_context()
        try:
            ctx1.recv_timeout = 50
            ctx2.recv_timeout = 500
            ctx1.send_timeout = 100
            ctx2.send_timeout = 1000

            assert ctx1.recv_timeout == 50
            assert ctx2.recv_timeout == 500
            assert ctx1.send_timeout == 100
            assert ctx2.send_timeout == 1000
        finally:
            ctx1.close()
            ctx2.close()


def test_context_timeout_triggers():
    """Setting a short recv_timeout on a context causes Timeout exception."""
    with pynng.Rep0(listen=addr + "-timeout") as s:
        ctx = s.new_context()
        try:
            ctx.recv_timeout = 1  # 1 ms
            with pytest.raises(pynng.Timeout):
                ctx.recv()
        finally:
            ctx.close()
