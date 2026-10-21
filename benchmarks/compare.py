#!/usr/bin/env python3
"""PyNNG Benchmark Comparison Tool.

Compares two benchmark JSON outputs (e.g. base branch vs PR branch) and
generates a GitHub-flavored Markdown report detailing speedups, regressions,
and latency improvements.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Tuple


def format_delta(delta: float, higher_is_better: bool = True) -> Tuple[str, str]:
    """Format delta percentage and assign status indicator."""
    abs_delta = abs(delta)
    if abs_delta < 5.0:
        return f"{delta:+.1f}%", "⚪ Neutral"

    is_improvement = (delta > 0) if higher_is_better else (delta < 0)
    if is_improvement:
        label = "Faster" if not higher_is_better else "Speedup"
        return f"**{delta:+.1f}%**", f"🚀 **{label}**"
    else:
        return f"**{delta:+.1f}%**", "⚠️ **Regression**"


def compare_benchmarks(
    base_file: str, pr_file: str, fail_threshold: float | None = None
) -> Tuple[str, bool]:
    with open(base_file, "r", encoding="utf-8") as f:
        base_data = json.load(f)
    with open(pr_file, "r", encoding="utf-8") as f:
        pr_data = json.load(f)

    base_meta = base_data.get("metadata", {})
    pr_meta = pr_data.get("metadata", {})

    base_map: Dict[str, Dict[str, Any]] = {}
    for b in base_data.get("benchmarks", []):
        key = f"{b['name']}|{b.get('transport', '')}|{b.get('protocol', '')}"
        base_map[key] = b

    pr_map: Dict[str, Dict[str, Any]] = {}
    for b in pr_data.get("benchmarks", []):
        key = f"{b['name']}|{b.get('transport', '')}|{b.get('protocol', '')}"
        pr_map[key] = b

    lines = []
    lines.append("## ⚡ PyNNG Performance Benchmark Report\n")
    lines.append(
        f"**Base:** `{base_meta.get('git_branch', 'base')}@{base_meta.get('git_commit', '')}` "
        f"| **PR:** `{pr_meta.get('git_branch', 'pr')}@{pr_meta.get('git_commit', '')}`\n"
    )

    lines.append("### 1. Throughput Benchmarks (Higher is better)")
    lines.append(
        "| Benchmark | Transport | Base msgs/s | PR msgs/s | Delta | Status |"
    )
    lines.append(
        "| :--- | :---: | :---: | :---: | :---: | :---: |"
    )

    has_hard_regression = False
    max_regression = 0.0

    # Throughput metrics
    for key, pr_bench in pr_map.items():
        if "msgs_per_sec" not in pr_bench:
            continue
        base_bench = base_map.get(key)
        name = pr_bench["name"]
        transport = pr_bench.get("transport", "-")
        pr_val = pr_bench["msgs_per_sec"]

        if base_bench and "msgs_per_sec" in base_bench:
            base_val = base_bench["msgs_per_sec"]
            delta = ((pr_val - base_val) / base_val) * 100.0 if base_val > 0 else 0.0
            delta_str, status = format_delta(delta, higher_is_better=True)
            if delta < -5.0:
                max_regression = max(max_regression, abs(delta))
                if fail_threshold and abs(delta) >= fail_threshold:
                    has_hard_regression = True
            lines.append(
                f"| **{name}** | `{transport}` | {base_val:,.1f} | {pr_val:,.1f} | {delta_str} | {status} |"
            )
        else:
            lines.append(
                f"| **{name}** | `{transport}` | *N/A* | {pr_val:,.1f} | *new* | ⚪ |"
            )

    lines.append("\n### 2. Round-Trip Latency Benchmarks (Lower is better)")
    lines.append(
        "| Benchmark | Transport | Base p50 | PR p50 | Base p99 | PR p99 | Delta (p50) | Status |"
    )
    lines.append(
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    )

    # Latency metrics
    for key, pr_bench in pr_map.items():
        if "p50_latency_us" not in pr_bench:
            continue
        base_bench = base_map.get(key)
        name = pr_bench["name"]
        transport = pr_bench.get("transport", "-")
        pr_p50 = pr_bench["p50_latency_us"]
        pr_p99 = pr_bench.get("p99_latency_us", 0.0)

        if base_bench and "p50_latency_us" in base_bench:
            base_p50 = base_bench["p50_latency_us"]
            base_p99 = base_bench.get("p99_latency_us", 0.0)
            delta = ((pr_p50 - base_p50) / base_p50) * 100.0 if base_p50 > 0 else 0.0
            delta_str, status = format_delta(delta, higher_is_better=False)
            if delta > 5.0:
                max_regression = max(max_regression, delta)
                if fail_threshold and delta >= fail_threshold:
                    has_hard_regression = True
            lines.append(
                f"| **{name}** | `{transport}` | {base_p50:.1f} µs | {pr_p50:.1f} µs | {base_p99:.1f} µs | {pr_p99:.1f} µs | {delta_str} | {status} |"
            )
        else:
            lines.append(
                f"| **{name}** | `{transport}` | *N/A* | {pr_p50:.1f} µs | *N/A* | {pr_p99:.1f} µs | *new* | ⚪ |"
            )

    lines.append("\n---")
    if has_hard_regression:
        lines.append(
            f"\n> ❌ **Regression Gate Failed**: A performance drop of {max_regression:.1f}% exceeded the allowed threshold of {fail_threshold:.1f}%.\n"
        )
    elif max_regression >= 5.0:
        lines.append(
            f"\n> ⚠️ **Notice**: Minor performance variance detected (max regression: {max_regression:.1f}%).\n"
        )
    else:
        lines.append(
            "\n> ✅ **Regression Gate Passed**: No performance regressions detected.\n"
        )

    return "\n".join(lines), has_hard_regression


def main():
    parser = argparse.ArgumentParser(
        description="Compare two PyNNG benchmark JSON files"
    )
    parser.add_argument("base", help="Path to base branch benchmark JSON")
    parser.add_argument("pr", help="Path to PR branch benchmark JSON")
    parser.add_argument(
        "--output", "-o", default=None, help="Output markdown file path"
    )
    parser.add_argument(
        "--fail-on-regression",
        type=float,
        default=None,
        help="Fail if any benchmark regresses by more than this percentage (e.g. 10.0)",
    )

    args = parser.parse_args()

    report, failed = compare_benchmarks(
        args.base, args.pr, fail_threshold=args.fail_on_regression
    )

    print(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport written to: {args.output}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
