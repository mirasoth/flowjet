"""fj CLI — any characters after the command are the agent query."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

from fj_ai import __version__
from fj_ai.argv import split_argv
from fj_ai.logging_setup import configure_cli_logging

USAGE = """\
fj — coding agent CLI (soothe-nano)

Usage:
  fj setup
  fj completion zsh|bash
  fj <query...>
  fj [options] [--] <query...>

Examples:
  fj who is your name
  fj 修改这个文件。
  fj explain how asyncio works in this repo
  eval "$(fj completion zsh)"

Everything after options is joined as the query (any Unicode).
Use ``--`` to force the rest of the line into the query (including leading dashes).
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fj",
        description="One-shot coding agent powered by soothe-nano",
        epilog="Any characters after options are the query.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"fj {__version__}",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="nano.yml path (default: ~/.soothe/config/nano.yml)",
    )
    parser.add_argument(
        "-t",
        "--thread",
        metavar="ID",
        help="LangGraph thread id (default: new fj-<uuid>)",
    )
    parser.add_argument(
        "-w",
        "--workspace",
        metavar="DIR",
        help="Workspace root for file/shell tools (default: cwd)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable token streaming; print final answer only",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show tool calls and custom events on stderr",
    )
    return parser


def _build_setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fj setup",
        description="Interactive setup for ~/.soothe/config/nano.yml",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="nano.yml path (default: ~/.soothe/config/nano.yml)",
    )
    return parser


def _namespace_with_command(ns: argparse.Namespace, command: str) -> argparse.Namespace:
    data: dict[str, Any] = vars(ns)
    data["command"] = command
    return argparse.Namespace(**data)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args; remaining tokens become the query string."""
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "setup":
        setup_args = _build_setup_parser().parse_args(raw[1:])
        setup_args.query_text = ""
        return _namespace_with_command(setup_args, "setup")
    if raw and raw[0] == "__complete":
        ns = argparse.Namespace(query_text="", complete_argv=raw[1:])
        return _namespace_with_command(ns, "__complete")
    if raw and raw[0] == "completion":
        ns = argparse.Namespace(query_text="", completion_argv=raw[1:])
        return _namespace_with_command(ns, "completion")

    option_tokens, query_tokens = split_argv(raw)
    args = _build_parser().parse_args(option_tokens)
    args.query_text = " ".join(query_tokens).strip()
    return _namespace_with_command(args, "query")


async def run_async(args: argparse.Namespace) -> int:
    if not args.query_text:
        sys.stderr.write(USAGE)
        return 2

    # Lazy: keep ``fj __complete`` / setup free of agent import cost.
    from fj_ai.agent import build_agent, open_sqlite_checkpointer
    from fj_ai.config import load_config
    from fj_ai.stream import invoke_query, stream_query

    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"error: failed to load config: {exc}\n")
        return 1

    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else None
    thread_id = args.thread or f"fj-{uuid.uuid4()}"

    try:
        async with open_sqlite_checkpointer(config) as checkpointer:
            agent = await build_agent(
                config,
                workspace=workspace,
                checkpointer=checkpointer,
            )
            if args.no_stream:
                await invoke_query(agent, args.query_text, thread_id=thread_id)
            else:
                await stream_query(
                    agent,
                    args.query_text,
                    thread_id=thread_id,
                    show_tool_calls=args.verbose,
                )
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    except Exception as exc:
        sys.stderr.write(f"error: {type(exc).__name__}: {exc}\n")
        return 1

    try:
        from fj_ai.completion.history import append_history

        append_history(args.query_text)
    except Exception:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        configure_cli_logging()
        args = parse_args(argv)
        # Keep interactive setup / completion off the event loop so Ctrl+C exits cleanly.
        if args.command == "setup":
            from fj_ai.setup_cmd import run_setup

            return run_setup(getattr(args, "config", None))
        if args.command == "__complete":
            from fj_ai.completion.cmd import run_complete

            return run_complete(getattr(args, "complete_argv", []))
        if args.command == "completion":
            from fj_ai.completion.cmd import run_completion_script

            return run_completion_script(getattr(args, "completion_argv", []))
        return asyncio.run(run_async(args))
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
