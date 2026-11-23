#!/usr/bin/env python3
"""Benchmark real agent tool calls through the os_sandbox pool.

Drives the **full agent tool-call path** — no toy ``echo`` commands:

    prompt → LLM → tool dispatch → BackendShellExecutor → sandbox execute() → result → LLM → answer

Uses :class:`ServerRuntimeBuilder` to build the production runtime (sandbox
manager + workspace resolver + thread pool + soothe agent), then sends
prompts that reliably trigger tool calls (file listing, file reading, code
execution) and measures:

* **End-to-end latency** — from ``stream_run`` to ``RunCompleted``
* **Tool call count** — how many tool calls the agent made per turn
* **Tool call duration** — ``ToolStarted`` → ``ToolCompleted`` per call
* **Sandbox execute latency** — the shell command time inside the sandbox
* **Memory consumption** — peak RSS during concurrent agent turns
* **Throughput** — concurrent turns per second at different pool caps

Requires a real LLM provider (DashScope). Set::

    DASHSCOPE_API_KEY=...
    DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

Usage::

    uv run python benchmarks/bench_agent_tool_calls.py
    uv run python benchmarks/bench_agent_tool_calls.py --caps 8 --rounds 2
    uv run python benchmarks/bench_agent_tool_calls.py --concurrency 4 --prompt list_files
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
from typing import Any

from flowjet.core.agent.wiring import ServerRuntimeBuilder
from flowjet.core.events import (
    RunCompleted,
    RunFailed,
    RunRequest,
    ToolCompleted,
    ToolStarted,
)

# ---------------------------------------------------------------------------
# RSS (platform-correct)
# ---------------------------------------------------------------------------


def _rss_kb() -> int:
    """Current process RSS in KiB (macOS returns bytes, Linux returns KiB)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if sys.platform == "darwin":
        return usage.ru_maxrss // 1024
    return usage.ru_maxrss


def _rss_children_kb() -> int:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    if sys.platform == "darwin":
        return usage.ru_maxrss // 1024
    return usage.ru_maxrss


# ---------------------------------------------------------------------------
# Workload: prompts that trigger real tool calls
# ---------------------------------------------------------------------------

# Each prompt is designed to reliably trigger at least one tool call.
# The workspace is seeded with files so the agent has something to inspect.
PROMPTS: dict[str, str] = {
    "list_files": "List all Python files in the workspace. Use the shell tool to run `find . -name '*.py'`.",
    "read_file": "Read the file main.py in the workspace and explain what it does in one sentence.",
    "run_code": "Run `python3 -c 'print(sum(range(1, 101)))'` in the shell and tell me the result.",
    "count_lines": "Count the total lines in all Python files. Run `find . -name '*.py' -exec wc -l {} +` in the shell.",
    "mixed": "Find all Python files, read main.py, then run `python3 -c 'print(2**10)'` and report all results.",
}


_WORKSPACE_FILES = {
    "main.py": "import sys\n\ndef main():\n    print('hello from sandbox')\n    return 0\n\nif __name__ == '__main__':\n    sys.exit(main())\n",
    "utils.py": "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
    "tests/test_main.py": "from main import main\n\ndef test_main(capsys):\n    assert main() == 0\n    captured = capsys.readouterr()\n    assert 'hello' in captured.out\n",
    "README.md": "# benchmark workspace\nA small Python project for sandbox benchmarking.\n",
    "data/sample.txt": "x" * 4096,
}


def _seed_workspace(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in _WORKSPACE_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return root


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class TurnMetrics:
    prompt_name: str
    end_to_end_ms: float = 0.0
    tool_calls: int = 0
    tool_durations_ms: list[float] = field(default_factory=list)
    completed: bool = False
    output_text: str = ""
    error: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class CapMetrics:
    cap: int
    turns: list[TurnMetrics] = field(default_factory=list)
    total_time_ms: float = 0.0
    peak_rss_self_kb: int = 0
    peak_rss_children_kb: int = 0

    def summary(self) -> dict:
        completed = [t for t in self.turns if t.completed]
        failed = [t for t in self.turns if not t.completed]
        e2e = [t.end_to_end_ms for t in completed]
        tool_counts = [t.tool_calls for t in completed]
        all_tool_durations = [d for t in completed for d in t.tool_durations_ms]

        def _stats(vals: list[float]) -> dict:
            if not vals:
                return {"n": 0}
            return {
                "n": len(vals),
                "p50_ms": round(statistics.median(vals), 1),
                "p95_ms": round(
                    sorted(vals)[int(len(vals) * 0.95)] if len(vals) > 1 else vals[0], 1
                ),
                "mean_ms": round(statistics.mean(vals), 1),
            }

        return {
            "cap": self.cap,
            "turns_total": len(self.turns),
            "turns_completed": len(completed),
            "turns_failed": len(failed),
            "end_to_end": _stats(e2e),
            "tool_calls_per_turn": {
                "min": min(tool_counts) if tool_counts else 0,
                "median": statistics.median(tool_counts) if tool_counts else 0,
                "max": max(tool_counts) if tool_counts else 0,
            },
            "tool_duration": _stats(all_tool_durations),
            "throughput_turns_per_sec": round(
                len(completed) / (self.total_time_ms / 1000) if self.total_time_ms > 0 else 0, 2
            ),
            "peak_rss_self_mb": round(self.peak_rss_self_kb / 1024, 1),
            "peak_rss_children_mb": round(self.peak_rss_children_kb / 1024, 1),
            "total_time_ms": round(self.total_time_ms, 1),
            "tokens_in": sum(t.input_tokens for t in completed),
            "tokens_out": sum(t.output_tokens for t in completed),
        }


# ---------------------------------------------------------------------------
# Benchmark driver
# ---------------------------------------------------------------------------


async def bench_cap(
    cap: int,
    prompts: list[tuple[str, str]],
    concurrency: int,
    rounds: int,
    workdir: Path,
    config_path: str,
    model: str,
) -> CapMetrics:
    """Benchmark one pool cap with real agent tool calls."""
    metrics = CapMetrics(cap=cap)

    # Build the full runtime: sandbox manager + workspace resolver + thread pool + agent.
    # sandbox_mode="auto" enables os_sandbox with the config's sandbox section.
    backend = ServerRuntimeBuilder.build(
        models=[model],
        config_path=config_path,
        home=str(workdir / "home"),
        cas_root=None,
        sync_source=None,
        sync_config_path=None,
        content_source=None,
        allow_external_workspace=True,
        pool_settings=None,
        checkpointer_policy="off",
        sandbox_mode="auto",
    )
    rss_self_before = _rss_kb()
    rss_children_before = _rss_children_kb()

    # Seed one workspace per concurrent slot.
    workspaces: list[Path] = []
    for i in range(concurrency):
        ws = _seed_workspace(workdir / f"cap{cap}" / f"ws{i}")
        workspaces.append(ws)

    try:
        # Warm-up: one turn to JIT-build the agent + spawn the first sandbox.
        print("    warm-up turn ...", file=sys.stderr, end="", flush=True)
        warm_prompt = prompts[0]
        warm_req = RunRequest(
            model=model,
            input_text=warm_prompt[1],
            session=f"warm-{cap}",
            metadata={"workspace": str(workspaces[0])},
        )
        try:
            async for _ in backend.stream_run(warm_req):
                pass
        except Exception as exc:
            print(f" warm-up failed: {exc}", file=sys.stderr)
        print(" done", file=sys.stderr)

        # Measured rounds: drive concurrent turns.
        t_start = time.monotonic()
        for r in range(rounds):
            tasks: list[asyncio.Task] = []
            for i in range(concurrency):
                prompt_name, prompt_text = prompts[(r * concurrency + i) % len(prompts)]
                session = f"bench-{cap}-r{r}-ws{i}"
                # Inject workspace via metadata so the resolver picks it up.
                req = RunRequest(
                    model=model,
                    input_text=prompt_text,
                    session=session,
                    metadata={"workspace": str(workspaces[i])},
                )
                tasks.append(asyncio.create_task(_drive_turn_direct(backend, req, prompt_name)))
            results = await asyncio.gather(*tasks)
            metrics.turns.extend(results)
        t_end = time.monotonic()

        metrics.total_time_ms = (t_end - t_start) * 1000
        metrics.peak_rss_self_kb = max(_rss_kb(), rss_self_before)
        metrics.peak_rss_children_kb = max(_rss_children_kb(), rss_children_before)
    finally:
        # Shutdown the backend (destroys sandbox pool).
        cleanup = getattr(backend, "shutdown", None)
        if cleanup:
            result = cleanup()
            if hasattr(result, "__await__"):
                await result

    return metrics


async def _drive_turn_direct(
    backend: Any,
    request: RunRequest,
    prompt_name: str,
) -> TurnMetrics:
    """Drive one turn via backend.stream_run and collect metrics."""
    metrics = TurnMetrics(prompt_name=prompt_name)
    t0 = time.monotonic()
    tool_starts: dict[str, float] = {}

    try:
        async for event in backend.stream_run(request):
            if isinstance(event, ToolStarted):
                cid = event.call_id or event.tool
                tool_starts[cid] = time.monotonic()
                metrics.tool_calls += 1
            elif isinstance(event, ToolCompleted):
                cid = event.call_id or event.tool
                start = tool_starts.pop(cid, None)
                if start is not None:
                    metrics.tool_durations_ms.append((time.monotonic() - start) * 1000)
                elif event.duration_ms is not None:
                    metrics.tool_durations_ms.append(float(event.duration_ms))
            elif isinstance(event, RunCompleted):
                metrics.completed = True
                metrics.output_text = event.output_text[:200]
                if event.usage:
                    metrics.input_tokens = event.usage.input_tokens
                    metrics.output_tokens = event.usage.output_tokens
            elif isinstance(event, RunFailed):
                metrics.error = event.message[:200]
    except Exception as exc:
        metrics.error = str(exc)[:200]

    metrics.end_to_end_ms = (time.monotonic() - t0) * 1000
    return metrics


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(all_metrics: list[CapMetrics], prompts_used: list[str]) -> None:
    print()
    print("=" * 90)
    print("  Agent Tool-Call Benchmark Report (real LLM → sandbox execute → result)")
    print("=" * 90)
    print(f"  host: {os.uname().sysname} {os.uname().machine}, {os.cpu_count()} logical CPUs")
    print(f"  prompts: {', '.join(prompts_used)}")
    print()

    # End-to-end latency table.
    print("  End-to-End Latency (ms):")
    print(
        f"  {'cap':>4}  {'turns':>6}  {'ok':>4}  {'fail':>4}  "
        f"{'e2e p50':>10}  {'e2e p95':>10}  {'e2e mean':>10}  "
        f"{'tools/turn':>12}  {'tool p50':>10}"
    )
    print(
        f"  {'----':>4}  {'------':>6}  {'----':>4}  {'----':>4}  "
        f"{'----------':>10}  {'----------':>10}  {'----------':>10}  "
        f"{'------------':>12}  {'----------':>10}"
    )
    for m in all_metrics:
        s = m.summary()
        e2e = s["end_to_end"]
        td = s["tool_duration"]
        print(
            f"  {m.cap:>4}  "
            f"{s['turns_total']:>6}  {s['turns_completed']:>4}  {s['turns_failed']:>4}  "
            f"{e2e.get('p50_ms', 0):>10}  {e2e.get('p95_ms', 0):>10}  {e2e.get('mean_ms', 0):>10}  "
            f"{s['tool_calls_per_turn']['median']:>12}  {td.get('p50_ms', 0):>10}"
        )

    # Throughput + memory.
    print()
    print("  Throughput & Memory:")
    print(
        f"  {'cap':>4}  {'turns/sec':>10}  {'peak RSS MB':>14}  "
        f"{'children MB':>14}  {'tokens in':>10}  {'tokens out':>10}  {'time ms':>10}"
    )
    print(
        f"  {'----':>4}  {'----------':>10}  {'--------------':>14}  "
        f"{'--------------':>14}  {'----------':>10}  {'----------':>10}  {'----------':>10}"
    )
    for m in all_metrics:
        s = m.summary()
        print(
            f"  {m.cap:>4}  "
            f"{s['throughput_turns_per_sec']:>10}  "
            f"{s['peak_rss_self_mb']:>14}  "
            f"{s['peak_rss_children_mb']:>14}  "
            f"{s['tokens_in']:>10}  {s['tokens_out']:>10}  "
            f"{s['total_time_ms']:>10}"
        )

    # Sample outputs.
    print()
    print("  Sample outputs (first completed turn per cap):")
    for m in all_metrics:
        first_ok = next((t for t in m.turns if t.completed), None)
        if first_ok:
            print(f"  cap={m.cap} [{first_ok.prompt_name}]: {first_ok.output_text[:120]}")
        else:
            first_err = next((t for t in m.turns if t.error), None)
            if first_err:
                print(f"  cap={m.cap} [{first_err.prompt_name}] ERROR: {first_err.error[:120]}")

    # Recommendations.
    print()
    print("  Recommendations:")
    ok_metrics = [m for m in all_metrics if m.summary()["turns_completed"] > 0]
    if ok_metrics:
        best_throughput = max(ok_metrics, key=lambda m: m.summary()["throughput_turns_per_sec"])
        best_latency = min(ok_metrics, key=lambda m: m.summary()["end_to_end"].get("p50_ms", 0))
        print(
            f"  • Best throughput: cap={best_throughput.cap} ({best_throughput.summary()['throughput_turns_per_sec']:.2f} turns/sec)"
        )
        print(
            f"  • Best latency:    cap={best_latency.cap} (e2e p50={best_latency.summary()['end_to_end'].get('p50_ms', 0):.0f} ms)"
        )
    cpu = os.cpu_count() or 1
    print(f"  • Host CPU count: {cpu}")
    print("  • Tool calls are the real bottleneck (LLM latency + sandbox execute)")
    print("  • For cvm-001 (8 vCPU / 16 GB): max_sandboxes=16 balances pool headroom vs memory")
    print("=" * 90)
    print()


def _print_json(all_metrics: list[CapMetrics]) -> None:
    output = {
        "host": {
            "sysname": os.uname().sysname,
            "machine": os.uname().machine,
            "cpu_count": os.cpu_count(),
        },
        "agent_tool_call_benchmark": [m.summary() for m in all_metrics],
    }
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def _write_bench_config(workdir: Path, max_sandboxes: int) -> Path:
    """Write a nano.yml for the benchmark with os_sandbox enabled."""
    config = f"""# Benchmark config — os_sandbox + DashScope LLM.
providers:
  - name: dashscope
    provider_type: openai
    api_base_url: "${{DASHSCOPE_BASE_URL}}"
    api_key: "${{DASHSCOPE_API_KEY}}"
    models:
      - glm-5.2
      - qwen3.6-flash

router_profiles:
  - name: bench
    router:
      default: "dashscope:qwen3.6-flash"
      fast: "dashscope:qwen3.6-flash"
      think: "dashscope:glm-5.2"

active_router_profile: bench

persistence:
  default_backend: sqlite

observability:
  log_file_level: WARNING

security:
  allow_paths_outside_workspace: true

sandbox:
  enabled: true
  max_sandboxes: {max_sandboxes}
  idle_timeout_seconds: 60
  min_free_bytes: 0
  on_deny: drop
  backend:
    type: os_sandbox
    os_sandbox:
      workspace_root: null
      linux_tier: auto
      allow_degraded: false
      default_timeout: 30
      env_allowlist: [PATH, LANG, LC_ALL, LC_CTYPE, TERM, TMPDIR, HOME]
      egress:
        enabled: false
"""
    path = workdir / "nano-bench.yml"
    path.write_text(config)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark real agent tool calls through the os_sandbox pool."
    )
    parser.add_argument(
        "--caps",
        default="4,8",
        help="Comma-separated pool cap values (default: 4,8)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Concurrent agent turns per round (default: 2)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="Measured rounds per cap (default: 1)",
    )
    parser.add_argument(
        "--prompts",
        default="list_files,read_file,run_code",
        help="Comma-separated prompt names (default: list_files,read_file,run_code)",
    )
    parser.add_argument(
        "--model",
        default="default",
        help="Model ID to use (default: default — resolved by router)",
    )
    parser.add_argument(
        "--workdir",
        default="/tmp/fj-bench-agent",
        help="Working directory (default: /tmp/fj-bench-agent)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )
    args = parser.parse_args()

    if not os.environ.get("DASHSCOPE_API_KEY"):
        print("ERROR: DASHSCOPE_API_KEY is required for real LLM tool calls.", file=sys.stderr)
        sys.exit(1)

    caps = [int(c.strip()) for c in args.caps.split(",")]
    prompt_names = [p.strip() for p in args.prompts.split(",")]
    prompts = [(name, PROMPTS[name]) for name in prompt_names]
    workdir = Path(args.workdir)

    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    # Write a config with the highest cap — we override per-bench via env.
    config_path = _write_bench_config(workdir, max_sandboxes=max(caps))

    print("agent tool-call benchmark", file=sys.stderr)
    print(f"  caps: {caps}", file=sys.stderr)
    print(f"  concurrency: {args.concurrency}", file=sys.stderr)
    print(f"  rounds: {args.rounds}", file=sys.stderr)
    print(f"  prompts: {prompt_names}", file=sys.stderr)
    print(f"  config: {config_path}", file=sys.stderr)
    print(f"  model: {args.model}", file=sys.stderr)
    print(file=sys.stderr)

    all_metrics: list[CapMetrics] = []

    async def _run() -> None:
        for cap in caps:
            # Override max_sandboxes via env for each cap.
            os.environ["FLOWJET_SANDBOX_MAX"] = str(cap)
            print(f"  → bench cap={cap} ...", file=sys.stderr, flush=True)
            m = await bench_cap(
                cap=cap,
                prompts=prompts,
                concurrency=args.concurrency,
                rounds=args.rounds,
                workdir=workdir,
                config_path=str(config_path),
                model=args.model,
            )
            all_metrics.append(m)
            s = m.summary()
            print(
                f"    done: {s['turns_completed']}/{s['turns_total']} ok, "
                f"{s['throughput_turns_per_sec']:.2f} turns/sec, "
                f"e2e p50={s['end_to_end'].get('p50_ms', 0):.0f}ms",
                file=sys.stderr,
            )

    asyncio.run(_run())

    if args.json:
        _print_json(all_metrics)
    else:
        _print_report(all_metrics, prompt_names)

    # Cleanup.
    if workdir.exists():
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
