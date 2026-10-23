"""Tests for the benchmarks/bench.py suite and edge-case validation."""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
import bench


def test_make_and_cleanup_ipc_addr():
    addr = bench.make_addr("ipc", "unit")
    assert addr.startswith("ipc://")
    path = addr[len("ipc://") :]
    with open(path, "w") as f:
        f.write("test")
    assert os.path.exists(path)
    bench.cleanup_ipc_addr("ipc", addr)
    assert not os.path.exists(path)


def test_bench_sync_stream_and_validation():
    for transport in ("inproc", "ipc", "tcp"):
        res = bench.bench_sync_stream(transport, count=5, payload_size=32, warmup=2, rounds=2)
        assert res["transport"] == transport
        assert res["count"] == 5
        assert res["msgs_per_sec"] > 0

    with pytest.raises(ValueError, match="count must be >= 1"):
        bench.bench_sync_stream("inproc", count=0, payload_size=32)
    with pytest.raises(ValueError, match="rounds must be >= 1"):
        bench.bench_sync_stream("inproc", count=5, payload_size=32, rounds=0)


@pytest.mark.asyncio
async def test_bench_async_stream_and_pingpong():
    res_stream = await bench.bench_async_stream("tcp", count=5, payload_size=32, warmup=2, rounds=2)
    assert res_stream["transport"] == "tcp"
    assert res_stream["count"] == 5
    assert res_stream["msgs_per_sec"] > 0

    res_pp = await bench.bench_async_pingpong("tcp", count=5, payload_size=32, warmup=2, rounds=2)
    assert res_pp["transport"] == "tcp"
    assert res_pp["count"] == 5
    assert res_pp["p50_latency_us"] >= res_pp["min_latency_us"]


@pytest.mark.asyncio
async def test_bench_async_context_fanin_small_count():
    """Verify count < num_contexts clamps items_per_ctx to >= 1 instead of ZeroDivisionError."""
    res = await bench.bench_async_context_fanin(
        count=3, num_contexts=8, payload_size=32, warmup=4, rounds=1
    )
    assert res["count"] == 16  # 1 item * 8 contexts * 2 (send+recv)
    assert res["msgs_per_sec"] > 0

    with pytest.raises(ValueError, match="count must be >= 1"):
        await bench.bench_async_context_fanin(count=0, num_contexts=4)
    with pytest.raises(ValueError, match="rounds must be >= 1"):
        await bench.bench_async_context_fanin(count=4, num_contexts=4, rounds=0)
