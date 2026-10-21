#!/usr/bin/env python3
"""PyNNG Benchmark Suite.

Measures asynchronous throughput (msgs/sec, MB/s) and latency percentiles
across transports (inproc, ipc, tcp) and protocols.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List

import pynng


def get_git_info() -> Dict[str, str]:
    """Retrieve current git branch and commit SHA."""
    info = {"commit": "unknown", "branch": "unknown"}
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        info["commit"] = sha[:8]
    except Exception:
        pass
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        info["branch"] = branch
    except Exception:
        pass
    return info


def make_addr(transport: str, test_id: str) -> str:
    """Generate a clean address for a given transport."""
    if transport == "inproc":
        return f"inproc://bench-{test_id}"
    elif transport == "ipc":
        path = os.path.join(tempfile.gettempdir(), f"pynng-bench-{test_id}.ipc")
        return f"ipc://{path}"
    elif transport == "tcp":
        return "tcp://127.0.0.1:0"
    raise ValueError(f"Unknown transport: {transport}")


# ---------------------------------------------------------------------------
# Benchmark 1: Async Pipelined Throughput (Pair0 asend / arecv)
# ---------------------------------------------------------------------------
async def bench_async_stream(
    transport: str, count: int, payload_size: int, warmup: int = 500
) -> Dict[str, Any]:
    test_id = f"stream-{int(time.time() * 1000)}"
    addr = make_addr(transport, test_id)
    payload = b"X" * payload_size

    with pynng.Pair0(listen=addr) as s1:
        dial_addr = s1.listeners[0].url if transport == "tcp" else addr
        with pynng.Pair0(dial=dial_addr) as s2:
            # Warmup
            async def warmup_run():
                for _ in range(warmup):
                    await s1.asend(payload)
                    await s2.arecv()

            await warmup_run()
            gc.collect()

            # Timed run
            async def sender():
                for _ in range(count):
                    await s1.asend(payload)

            async def receiver():
                for _ in range(count):
                    await s2.arecv()

            start = time.perf_counter()
            await asyncio.gather(sender(), receiver())
            elapsed = time.perf_counter() - start

    msgs_per_sec = count / elapsed
    mb_per_sec = (count * payload_size) / (elapsed * 1024 * 1024)
    avg_latency_us = (elapsed / count) * 1e6

    return {
        "name": "Async Stream Throughput",
        "protocol": "Pair0",
        "transport": transport,
        "payload_bytes": payload_size,
        "count": count,
        "elapsed_sec": round(elapsed, 4),
        "msgs_per_sec": round(msgs_per_sec, 1),
        "mb_per_sec": round(mb_per_sec, 2),
        "avg_latency_us": round(avg_latency_us, 2),
    }


# ---------------------------------------------------------------------------
# Benchmark 2: Ping-Pong Round-Trip Latency (Pair0 RTT percentiles)
# ---------------------------------------------------------------------------
async def bench_async_pingpong(
    transport: str, count: int, payload_size: int, warmup: int = 500
) -> Dict[str, Any]:
    test_id = f"pingpong-{int(time.time() * 1000)}"
    addr = make_addr(transport, test_id)
    payload = b"P" * payload_size

    with pynng.Pair0(listen=addr) as s1:
        dial_addr = s1.listeners[0].url if transport == "tcp" else addr
        with pynng.Pair0(dial=dial_addr) as s2:
            # Echo server coroutine
            stop_server = False

            async def echo_server():
                while not stop_server:
                    try:
                        msg = await s2.arecv()
                        await s2.asend(msg)
                    except Exception:
                        break

            server_task = asyncio.create_task(echo_server())

            # Warmup
            for _ in range(warmup):
                await s1.asend(payload)
                await s1.arecv()

            gc.collect()

            # Timed measurements
            latencies_ns: List[int] = []
            for _ in range(count):
                t0 = time.perf_counter_ns()
                await s1.asend(payload)
                await s1.arecv()
                t1 = time.perf_counter_ns()
                latencies_ns.append(t1 - t0)

            stop_server = True
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    latencies_ns.sort()
    n = len(latencies_ns)
    p50 = latencies_ns[int(n * 0.50)] / 1000.0
    p90 = latencies_ns[int(n * 0.90)] / 1000.0
    p95 = latencies_ns[int(n * 0.95)] / 1000.0
    p99 = latencies_ns[int(n * 0.99)] / 1000.0
    min_us = latencies_ns[0] / 1000.0
    max_us = latencies_ns[-1] / 1000.0
    mean_us = (sum(latencies_ns) / n) / 1000.0
    total_sec = sum(latencies_ns) / 1e9
    rtt_per_sec = count / total_sec

    return {
        "name": "Async Ping-Pong Latency",
        "protocol": "Pair0",
        "transport": transport,
        "payload_bytes": payload_size,
        "count": count,
        "rtt_per_sec": round(rtt_per_sec, 1),
        "mean_latency_us": round(mean_us, 2),
        "min_latency_us": round(min_us, 2),
        "p50_latency_us": round(p50, 2),
        "p90_latency_us": round(p90, 2),
        "p95_latency_us": round(p95, 2),
        "p99_latency_us": round(p99, 2),
        "max_latency_us": round(max_us, 2),
    }


# ---------------------------------------------------------------------------
# Benchmark 3: Multi-Context Concurrent Fan-In (Rep0 / Req0 Context arecv)
# ---------------------------------------------------------------------------
async def bench_async_context_fanin(
    count: int, num_contexts: int = 4, payload_size: int = 64
) -> Dict[str, Any]:
    addr = make_addr("inproc", f"ctx-fanin-{int(time.time() * 1000)}")
    payload = b"C" * payload_size
    items_per_ctx = count // num_contexts

    with pynng.Rep0(listen=addr) as rep, pynng.Req0(dial=addr) as req:
        rep_contexts = [rep.new_context() for _ in range(num_contexts)]
        req_contexts = [req.new_context() for _ in range(num_contexts)]

        async def worker(c_rep, c_req):
            for _ in range(items_per_ctx):
                await c_req.asend(payload)
                msg = await c_rep.arecv()
                await c_rep.asend(msg)
                await c_req.arecv()

        gc.collect()
        start = time.perf_counter()
        tasks = [
            asyncio.create_task(worker(rep_contexts[i], req_contexts[i]))
            for i in range(num_contexts)
        ]
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start

        for c in rep_contexts + req_contexts:
            c.close()

    total_msgs = items_per_ctx * num_contexts * 2  # send + recv on both
    msgs_per_sec = total_msgs / elapsed

    return {
        "name": f"Context Fan-In ({num_contexts} contexts)",
        "protocol": "Req0/Rep0 Contexts",
        "transport": "inproc",
        "payload_bytes": payload_size,
        "count": total_msgs,
        "elapsed_sec": round(elapsed, 4),
        "msgs_per_sec": round(msgs_per_sec, 1),
        "avg_latency_us": round((elapsed / total_msgs) * 1e6, 2),
    }


# ---------------------------------------------------------------------------
# Benchmark 4: Synchronous Baseline (Pair0 send / recv)
# ---------------------------------------------------------------------------
def bench_sync_stream(
    transport: str, count: int, payload_size: int, warmup: int = 500
) -> Dict[str, Any]:
    test_id = f"sync-{int(time.time() * 1000)}"
    addr = make_addr(transport, test_id)
    payload = b"S" * payload_size

    with pynng.Pair0(listen=addr) as s1:
        dial_addr = s1.listeners[0].url if transport == "tcp" else addr
        with pynng.Pair0(dial=dial_addr) as s2:
            for _ in range(warmup):
                s1.send(payload)
                s2.recv()

            gc.collect()
            start = time.perf_counter()
            for _ in range(count):
                s1.send(payload)
                s2.recv()
            elapsed = time.perf_counter() - start

    msgs_per_sec = count / elapsed
    mb_per_sec = (count * payload_size) / (elapsed * 1024 * 1024)

    return {
        "name": "Sync Baseline (send/recv)",
        "protocol": "Pair0",
        "transport": transport,
        "payload_bytes": payload_size,
        "count": count,
        "elapsed_sec": round(elapsed, 4),
        "msgs_per_sec": round(msgs_per_sec, 1),
        "mb_per_sec": round(mb_per_sec, 2),
        "avg_latency_us": round((elapsed / count) * 1e6, 2),
    }


# ---------------------------------------------------------------------------
# CLI Runner and Formatting
# ---------------------------------------------------------------------------
def run_all_benchmarks(
    count: int, transports: List[str], payload_size: int
) -> Dict[str, Any]:
    git_info = get_git_info()
    suite_data: Dict[str, Any] = {
        "metadata": {
            "timestamp": time.time(),
            "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "python_version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "os": platform.system(),
            "arch": platform.machine(),
            "git_commit": git_info["commit"],
            "git_branch": git_info["branch"],
        },
        "benchmarks": [],
    }

    print("\n" + "=" * 80)
    print(
        f"  PyNNG Performance Benchmark Suite  [{git_info['branch']}@{git_info['commit']}]"
    )
    print("=" * 80)
    print(f"Python: {sys.version.split()[0]} ({platform.python_implementation()})")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Payload Size: {payload_size} bytes  |  Iterations per run: {count:,}")
    print("-" * 80)

    # 1. Sync Baseline
    print("\n[1/4] Running Synchronous Baseline...")
    for t in transports:
        res = bench_sync_stream(t, count, payload_size)
        suite_data["benchmarks"].append(res)
        print(f"  - {t:<8}: {res['msgs_per_sec']:>10,f} msgs/sec  ({res['avg_latency_us']:>6.1f} µs/msg)")

    # 2. Async Stream Throughput
    print("\n[2/4] Running Async Pipelined Stream (Throughput)...")
    for t in transports:
        res = asyncio.run(bench_async_stream(t, count, payload_size))
        suite_data["benchmarks"].append(res)
        print(f"  - {t:<8}: {res['msgs_per_sec']:>10,f} msgs/sec  ({res['avg_latency_us']:>6.1f} µs/msg)  [{res['mb_per_sec']:>6.2f} MB/s]")

    # 3. Async Ping-Pong Round-Trip Latency
    print("\n[3/4] Running Async Ping-Pong (Round-Trip Latency)...")
    for t in transports:
        # For ping-pong, default count to min(count, 5000) for fast RTT distribution
        pp_count = min(count, 5000)
        res = asyncio.run(bench_async_pingpong(t, pp_count, payload_size))
        suite_data["benchmarks"].append(res)
        print(
            f"  - {t:<8}: mean={res['mean_latency_us']:>5.1f}µs | "
            f"p50={res['p50_latency_us']:>5.1f}µs | "
            f"p95={res['p95_latency_us']:>5.1f}µs | "
            f"p99={res['p99_latency_us']:>5.1f}µs | "
            f"RTT/sec={res['rtt_per_sec']:>8,f}"
        )

    # 4. Multi-Context Concurrent Fan-In
    print("\n[4/4] Running Context Multi-Worker Fan-In...")
    for num_ctx in [4, 8]:
        res = asyncio.run(bench_async_context_fanin(count, num_contexts=num_ctx, payload_size=payload_size))
        suite_data["benchmarks"].append(res)
        print(f"  - {num_ctx} contexts: {res['msgs_per_sec']:>10,f} msgs/sec  ({res['avg_latency_us']:>6.1f} µs/msg)")

    print("\n" + "=" * 80 + "\n")
    return suite_data


def main():
    parser = argparse.ArgumentParser(description="PyNNG Benchmark Suite")
    parser.add_argument(
        "--count",
        "-n",
        type=int,
        default=10000,
        help="Number of iterations for throughput tests (default: 10000)",
    )
    parser.add_argument(
        "--transports",
        "-t",
        type=str,
        default="inproc,ipc,tcp",
        help="Comma-separated transports to benchmark (default: inproc,ipc,tcp)",
    )
    parser.add_argument(
        "--payload-size",
        "-s",
        type=int,
        default=64,
        help="Payload size in bytes (default: 64)",
    )
    parser.add_argument(
        "--json",
        "-j",
        type=str,
        default=None,
        help="Path to save JSON benchmark results",
    )

    args = parser.parse_args()
    transports = [t.strip() for t in args.transports.split(",") if t.strip()]

    suite_data = run_all_benchmarks(
        count=args.count, transports=transports, payload_size=args.payload_size
    )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(suite_data, f, indent=2)
        print(f"Benchmark results saved to: {args.json}\n")


if __name__ == "__main__":
    main()
