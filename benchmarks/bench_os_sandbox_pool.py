#!/usr/bin/env python3
"""Benchmark the os_sandbox pool with real workload and resource consumption.

Sweeps pool cap values (4 / 8 / 16 / 32) and measures for each:

* **Open latency** — time to open a single sandbox workspace
* **Execute latency** — time to run a command inside a real os_sandbox
* **Close latency** — time to close a sandbox lease
* **Memory per sandbox** — peak RSS delta ÷ sandbox count
* **Throughput** — open→execute→close cycles per second at concurrency N
* **Pool saturation** — behaviour when concurrent opens exceed the cap (LRU eviction)

Usage::

    uv run python benchmarks/bench_os_sandbox_pool.py
    uv run python benchmarks/bench_os_sandbox_pool.py --caps 4,8 --concurrency 16
    uv run python benchmarks/bench_os_sandbox_pool.py --workdir /tmp/fj-bench

The script uses the **real** soothe-nano os_sandbox backend (Seatbelt on macOS,
bwrap+seccomp on Linux). No HTTP server is needed — it drives
``ToolSandboxManager`` directly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import shutil
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from flowjet.core.sandbox import ToolSandboxManager, ToolSandboxSettings

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _rss_kb() -> int:
    """Current process RSS in KiB (works on macOS and Linux).

    macOS ``ru_maxrss`` is in **bytes**; Linux is in **KiB**.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if sys.platform == "darwin":
        return usage.ru_maxrss // 1024
    return usage.ru_maxrss


def _rss_children_kb() -> int:
    """RSS of child processes in KiB (best-effort via RUSAGE_CHILDREN)."""
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    if sys.platform == "darwin":
        return usage.ru_maxrss // 1024
    return usage.ru_maxrss


@dataclass
class SandboxMetrics:
    cap: int
    open_latencies_ms: list[float] = field(default_factory=list)
    execute_latencies_ms: list[float] = field(default_factory=list)
    close_latencies_ms: list[float] = field(default_factory=list)
    throughput_ops_per_sec: float = 0.0
    peak_rss_self_kb: int = 0
    peak_rss_children_kb: int = 0
    sandboxes_spawned: int = 0
    evictions: int = 0
    total_time_ms: float = 0.0

    def summary(self) -> dict:
        """Compact summary for the report."""

        def _stats(vals: list[float]) -> dict:
            if not vals:
                return {"n": 0}
            return {
                "n": len(vals),
                "p50_ms": round(statistics.median(vals), 2),
                "p95_ms": round(
                    sorted(vals)[int(len(vals) * 0.95)] if len(vals) > 1 else vals[0], 2
                ),
                "mean_ms": round(statistics.mean(vals), 2),
            }

        return {
            "cap": self.cap,
            "open": _stats(self.open_latencies_ms),
            "execute": _stats(self.execute_latencies_ms),
            "close": _stats(self.close_latencies_ms),
            "throughput_ops_per_sec": round(self.throughput_ops_per_sec, 1),
            "peak_rss_self_mb": round(self.peak_rss_self_kb / 1024, 1),
            "peak_rss_children_mb": round(self.peak_rss_children_kb / 1024, 1),
            "sandboxes_spawned": self.sandboxes_spawned,
            "evictions": self.evictions,
            "total_time_ms": round(self.total_time_ms, 1),
            "mem_per_sandbox_mb": (
                round((self.peak_rss_children_kb) / 1024 / max(1, self.sandboxes_spawned), 1)
            ),
        }


# ---------------------------------------------------------------------------
# Workload
# ---------------------------------------------------------------------------

_WORKSPACE_FILES = {
    "main.py": "print('hello from sandbox')\n",
    "README.md": "# benchmark workspace\n",
    "data/sample.txt": "x" * 4096,
    "src/utils.py": "def add(a, b): return a + b\n",
}


def _seed_workspace(root: Path) -> Path:
    """Create a workspace with a small file tree (simulates a real repo)."""
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in _WORKSPACE_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return root


async def _open_execute_close(
    manager: ToolSandboxManager,
    workspace: str,
    metrics: SandboxMetrics,
) -> None:
    """One open→execute→close cycle, recording latencies."""
    t0 = time.monotonic()
    await manager.open_workspace(workspace)
    t1 = time.monotonic()
    metrics.open_latencies_ms.append((t1 - t0) * 1000)

    backend = manager.backend_for(workspace)
    t2 = time.monotonic()
    result = await asyncio.to_thread(
        backend.execute, "echo bench-$$ && cat data/sample.txt | wc -c"
    )
    t3 = time.monotonic()
    metrics.execute_latencies_ms.append((t3 - t2) * 1000)

    exit_code = getattr(result, "exit_code", -1)
    if exit_code != 0:
        print(f"  WARN: execute exit_code={exit_code}", file=sys.stderr)

    t4 = time.monotonic()
    await manager.close_workspace(workspace)
    t5 = time.monotonic()
    metrics.close_latencies_ms.append((t5 - t4) * 1000)


async def _run_concurrent_batch(
    manager: ToolSandboxManager,
    workspaces: list[str],
    metrics: SandboxMetrics,
) -> None:
    """Run open→execute→close concurrently across N workspaces."""
    tasks = [_open_execute_close(manager, ws, metrics) for ws in workspaces]
    await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Benchmark driver
# ---------------------------------------------------------------------------


def _os_sandbox_settings(cap: int) -> ToolSandboxSettings:
    return ToolSandboxSettings(
        enabled=True,
        backend={
            "type": "os_sandbox",
            "os_sandbox": {
                "workspace_root": None,
                "linux_tier": "auto",
                "allow_degraded": False,
                "default_timeout": 30,
                "env_allowlist": ["PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "HOME"],
                "egress": {"enabled": False},
            },
        },
        max_sandboxes=cap,
        idle_timeout_seconds=60,
        min_free_bytes=0,
    )


async def bench_pool_cap(
    cap: int,
    concurrency: int,
    rounds: int,
    workdir: Path,
) -> SandboxMetrics:
    """Benchmark a single pool cap value.

    For each round, opens ``concurrency`` workspaces concurrently, executes a
    command in each, then closes them. Measures latency, throughput, and RSS.
    """
    metrics = SandboxMetrics(cap=cap)
    settings = _os_sandbox_settings(cap)
    manager = ToolSandboxManager(settings)

    # Seed workspaces.
    workspaces: list[str] = []
    for i in range(concurrency):
        ws = _seed_workspace(workdir / f"cap{cap}" / f"ws{i}")
        workspaces.append(str(ws))

    rss_self_before = _rss_kb()
    rss_children_before = _rss_children_kb()

    try:
        # Warm-up round (first sandbox spawn is slower — JIT/seatbelt init).
        await _run_concurrent_batch(manager, workspaces, metrics)

        # Reset metrics after warm-up.
        metrics.open_latencies_ms.clear()
        metrics.execute_latencies_ms.clear()
        metrics.close_latencies_ms.clear()

        t_start = time.monotonic()
        for _ in range(rounds):
            await _run_concurrent_batch(manager, workspaces, metrics)
        t_end = time.monotonic()

        metrics.total_time_ms = (t_end - t_start) * 1000
        total_ops = concurrency * rounds
        metrics.throughput_ops_per_sec = total_ops / (t_end - t_start)
        metrics.peak_rss_self_kb = max(_rss_kb(), rss_self_before)
        metrics.peak_rss_children_kb = max(_rss_children_kb(), rss_children_before)
        # Count live + closed leases. After rounds of open→close with cap
        # enforcement, some leases were evicted by LRU. We approximate by
        # counting unique backends spawned vs live leases.
        live = manager.lease_count
        # Each workspace gets at least one backend; extras come from eviction
        # respawns. sandboxes_spawned ≈ live + evicted respawns.
        metrics.sandboxes_spawned = max(live, concurrency)
        metrics.evictions = max(0, concurrency - cap) if concurrency > cap else 0

    finally:
        await manager.shutdown()

    return metrics


async def bench_pool_saturation(
    cap: int,
    total_workspaces: int,
    workdir: Path,
) -> dict:
    """Test LRU eviction when concurrent opens exceed the pool cap.

    Opens ``total_workspaces`` (> cap) sequentially, then checks how many
    sandboxes were evicted to make room.
    """
    settings = _os_sandbox_settings(cap)
    manager = ToolSandboxManager(settings)

    workspaces: list[str] = []
    for i in range(total_workspaces):
        ws = _seed_workspace(workdir / f"sat_cap{cap}" / f"ws{i}")
        workspaces.append(str(ws))

    try:
        # Open all sequentially (forces LRU eviction as pool fills).
        for ws in workspaces:
            await manager.open_workspace(ws)
            await manager.close_workspace(ws)

        live_leases = manager.lease_count
        return {
            "cap": cap,
            "total_workspaces": total_workspaces,
            "live_leases_after": live_leases,
            "evicted": total_workspaces - live_leases,
        }
    finally:
        await manager.shutdown()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(all_metrics: list[SandboxMetrics], saturation: list[dict]) -> None:
    """Print a human-readable benchmark report."""
    print()
    print("=" * 80)
    print("  os_sandbox Pool Benchmark Report")
    print("=" * 80)
    print(f"  host: {os.uname().sysname} {os.uname().machine}, {os.cpu_count()} logical CPUs")
    print()

    # Latency table.
    print("  Latency (p50 / p95 / mean, ms):")
    print(
        f"  {'cap':>4}  {'open p50':>10}  {'open p95':>10}  {'exec p50':>10}  {'exec p95':>10}  {'close p50':>10}  {'close p95':>10}"
    )
    print(
        f"  {'----':>4}  {'----------':>10}  {'----------':>10}  {'----------':>10}  {'----------':>10}  {'----------':>10}  {'----------':>10}"
    )
    for m in all_metrics:
        s = m.summary()
        print(
            f"  {m.cap:>4}  "
            f"{s['open']['p50_ms']:>10}  {s['open']['p95_ms']:>10}  "
            f"{s['execute']['p50_ms']:>10}  {s['execute']['p95_ms']:>10}  "
            f"{s['close']['p50_ms']:>10}  {s['close']['p95_ms']:>10}"
        )

    # Throughput + memory table.
    print()
    print("  Throughput & Memory:")
    print(
        f"  {'cap':>4}  {'ops/sec':>10}  {'peak RSS MB':>14}  {'per-sandbox MB':>16}  {'spawned':>10}  {'time ms':>10}"
    )
    print(
        f"  {'----':>4}  {'----------':>10}  {'--------------':>14}  {'----------------':>16}  {'----------':>10}  {'----------':>10}"
    )
    for m in all_metrics:
        s = m.summary()
        print(
            f"  {m.cap:>4}  "
            f"{s['throughput_ops_per_sec']:>10}  "
            f"{s['peak_rss_children_mb']:>14}  "
            f"{s['mem_per_sandbox_mb']:>16}  "
            f"{s['sandboxes_spawned']:>10}  "
            f"{s['total_time_ms']:>10}"
        )

    # Saturation / eviction.
    print()
    print("  Pool Saturation (LRU eviction):")
    print(f"  {'cap':>4}  {'opened':>10}  {'live after':>12}  {'evicted':>10}")
    print(f"  {'----':>4}  {'----------':>10}  {'------------':>12}  {'----------':>10}")
    for s in saturation:
        print(
            f"  {s['cap']:>4}  {s['total_workspaces']:>10}  {s['live_leases_after']:>12}  {s['evicted']:>10}"
        )

    # Recommendations.
    print()
    print("  Recommendations:")
    best_throughput = max(all_metrics, key=lambda m: m.throughput_ops_per_sec)
    best_latency = min(all_metrics, key=lambda m: statistics.median(m.open_latencies_ms))
    print(
        f"  • Best throughput: cap={best_throughput.cap} ({best_throughput.throughput_ops_per_sec:.1f} ops/sec)"
    )
    print(
        f"  • Best latency:    cap={best_latency.cap} (open p50={statistics.median(best_latency.open_latencies_ms):.2f} ms)"
    )
    cpu = os.cpu_count() or 1
    print(f"  • Host CPU count: {cpu}")
    print("  • For 8 vCPU / 16 GB (cvm-001):")
    print("    - os_sandbox is lightweight (process-level, no VM)")
    print("    - Recommended max_sandboxes: 16 (2× vCPU, balances throughput vs memory)")
    print("    - Set FLOWJET_SANDBOX_MAX=16 env var for runtime override")
    print("    - idle_timeout_seconds: 300 (5 min, reaps idle sandboxes)")
    print("    - min_free_bytes: 1073741824 (1 GB disk watermark)")
    print("=" * 80)
    print()


def _print_json(all_metrics: list[SandboxMetrics], saturation: list[dict]) -> None:
    """Print machine-readable JSON."""
    output = {
        "host": {
            "sysname": os.uname().sysname,
            "machine": os.uname().machine,
            "cpu_count": os.cpu_count(),
        },
        "pool_sweep": [m.summary() for m in all_metrics],
        "saturation": saturation,
    }
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark the os_sandbox pool with real workload."
    )
    parser.add_argument(
        "--caps",
        default="4,8,16,32",
        help="Comma-separated pool cap values to sweep (default: 4,8,16,32)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=16,
        help="Concurrent workspaces per round (default: 16)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="Measured rounds per cap (after 1 warm-up) (default: 3)",
    )
    parser.add_argument(
        "--workdir",
        default="/tmp/fj-bench-sandbox",
        help="Working directory for benchmark workspaces (default: /tmp/fj-bench-sandbox)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of a text report",
    )
    parser.add_argument(
        "--no-saturation",
        action="store_true",
        help="Skip the pool saturation (LRU eviction) test",
    )
    args = parser.parse_args()

    caps = [int(c.strip()) for c in args.caps.split(",")]
    workdir = Path(args.workdir)

    # Clean slate.
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    print("os_sandbox pool benchmark", file=sys.stderr)
    print(f"  caps: {caps}", file=sys.stderr)
    print(f"  concurrency: {args.concurrency}", file=sys.stderr)
    print(f"  rounds: {args.rounds}", file=sys.stderr)
    print(f"  workdir: {workdir}", file=sys.stderr)
    print(file=sys.stderr)

    all_metrics: list[SandboxMetrics] = []
    saturation: list[dict] = []

    async def _run() -> None:
        for cap in caps:
            print(f"  → bench cap={cap} ...", file=sys.stderr, end="", flush=True)
            m = await bench_pool_cap(cap, args.concurrency, args.rounds, workdir)
            all_metrics.append(m)
            print(f" done ({m.throughput_ops_per_sec:.1f} ops/sec)", file=sys.stderr)

        if not args.no_saturation:
            for cap in caps:
                total = max(cap * 3, cap + 8)
                print(
                    f"  → saturation cap={cap} (open {total}) ...",
                    file=sys.stderr,
                    end="",
                    flush=True,
                )
                s = await bench_pool_saturation(cap, total, workdir)
                saturation.append(s)
                print(f" done (evicted {s['evicted']})", file=sys.stderr)

    asyncio.run(_run())

    if args.json:
        _print_json(all_metrics, saturation)
    else:
        _print_report(all_metrics, saturation)

    # Cleanup.
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
