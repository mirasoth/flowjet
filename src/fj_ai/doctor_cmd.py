"""``fj doctor`` — progressive diagnosis via soothe-nano diagnose API."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, TextIO

_STATUS_SYMBOLS = {
    "ok": "✓",
    "warning": "⚠",
    "error": "✗",
    "info": "ℹ",  # noqa: RUF001
    "skipped": "○",
}

_STATUS_PLAIN = {
    "ok": "[OK]",
    "warning": "[WARN]",
    "error": "[ERROR]",
    "info": "[INFO]",
    "skipped": "[SKIP]",
}

_SEVERITY = {
    "ok": 0,
    "info": 1,
    "skipped": 2,
    "warning": 3,
    "error": 4,
}


def _build_parser() -> argparse.ArgumentParser:
    from fj_ai.agent import default_config_path
    from fj_ai.cli import resolve_cli_prog

    parser = argparse.ArgumentParser(
        prog=f"{resolve_cli_prog()} doctor",
        description="Diagnose FlowJet / soothe-nano runtime readiness (tool deps, providers, …)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help=f"Alternate nano.yml (default: {default_config_path()})",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Include deep nano categories (MCP, vector stores, models, protocols)",
    )
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="Live-invoke the default router model (may call the provider)",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json"),
        default="text",
        help="Report format (default: text progressive)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in text output",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning"),
        default="error",
        help="Exit non-zero when status reaches this severity (default: error)",
    )
    return parser


def parse_doctor_args(argv: list[str]) -> argparse.Namespace:
    """Parse ``fj doctor`` argv (tokens after the ``doctor`` word)."""
    return _build_parser().parse_args(argv)


def _worst_status(categories: list[dict[str, Any]]) -> str:
    worst = "ok"
    for cat in categories:
        status = str(cat.get("status", "ok"))
        if _SEVERITY.get(status, 0) > _SEVERITY.get(worst, 0):
            worst = status
    return worst


def _exit_code(overall: str, *, fail_on: str) -> int:
    if fail_on == "warning":
        return 1 if _SEVERITY.get(overall, 0) >= _SEVERITY["warning"] else 0
    return 1 if overall == "error" else 0


def _symbol(status: str, *, use_color: bool) -> str:
    table = _STATUS_SYMBOLS if use_color else _STATUS_PLAIN
    return table.get(status, status)


def _print_category(cat: dict[str, Any], *, use_color: bool, stream: TextIO) -> None:
    status = str(cat.get("status", "ok"))
    title = str(cat.get("category", "unknown")).replace("_", " ").title()
    stream.write(f"{_symbol(status, use_color=use_color)} {title}\n")
    for check in cat.get("checks") or []:
        if not isinstance(check, dict):
            continue
        cstatus = str(check.get("status", "ok"))
        msg = str(check.get("message", ""))
        stream.write(f"  {_symbol(cstatus, use_color=use_color)} {msg}\n")
        details = check.get("details") or {}
        if cstatus in ("error", "warning") and isinstance(details, dict):
            for key in ("impact", "remediation"):
                if key in details:
                    stream.write(f"    └─ {key.title()}: {details[key]}\n")
    stream.write("\n")
    stream.flush()


def _print_summary(overall: str, *, use_color: bool, stream: TextIO) -> None:
    stream.write("━" * 60 + "\n")
    stream.write(f"Overall Status: {_symbol(overall, use_color=use_color)} {overall.upper()}\n")


async def _run_diagnose(
    config: Any | None,
    *,
    deep: bool,
    live_llm: bool,
) -> list[dict[str, Any]]:
    try:
        from soothe_nano.diagnose import diagnose
    except ImportError as exc:
        raise RuntimeError(
            "soothe-nano diagnose API unavailable; upgrade soothe-nano "
            "(fj doctor requires soothe-nano>=1.0.8)"
        ) from exc
    return await diagnose(config, deep=deep, live_llm=live_llm)


def run_doctor(argv: list[str] | None = None) -> int:
    """Entry point for ``fj doctor`` (sync wrapper around async diagnose)."""
    import asyncio

    args = parse_doctor_args(list(argv or []))
    try:
        return asyncio.run(_run_doctor_async(args))
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130


async def _run_doctor_async(args: argparse.Namespace) -> int:
    from fj_ai.agent import load_config

    config: Any | None
    try:
        config = load_config(getattr(args, "config", None))
    except Exception as exc:
        sys.stderr.write(f"warning: config load failed ({exc}); running limited checks\n")
        config = None

    try:
        categories = await _run_diagnose(
            config,
            deep=bool(args.deep),
            live_llm=bool(args.live_llm),
        )
    except RuntimeError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"error: diagnose failed: {exc}\n")
        return 1

    overall = _worst_status(categories)
    use_color = not bool(args.no_color) and sys.stdout.isatty()

    if args.output_format == "json":
        payload = {
            "overall_status": overall,
            "categories": categories,
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write("fj doctor — progressive diagnosis\n")
        sys.stdout.write("━" * 60 + "\n\n")
        sys.stdout.flush()
        for cat in categories:
            _print_category(cat, use_color=use_color, stream=sys.stdout)
        _print_summary(overall, use_color=use_color, stream=sys.stdout)

    return _exit_code(overall, fail_on=str(args.fail_on))
