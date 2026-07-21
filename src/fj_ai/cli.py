"""fj CLI — any characters after the command are the agent query."""

from __future__ import annotations

import argparse
import asyncio
import sys
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
  fj -l
  fj -l -n 50
  fj --reset
  fj --reset <query...>
  fj <query...>
  fj [options] [--] <query...>

Examples:
  fj who is your name
  fj explain this file
  fj explain how asyncio works in this repo
  fj -l
  fj -l -n 5
  fj --reset
  fj --reset start a fresh conversation
  fj -t <thread-id> continue this conversation
  eval "$(fj completion zsh)"

Queries continue the latest active thread by default.
Use ``--reset`` to start a new active thread.
Everything after options is joined as the query (any Unicode).
Use ``--`` to force the rest of the line into the query (including leading dashes).
"""


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Keep short flags on one line; long option strings wrap help cleanly."""

    def __init__(self, prog: str) -> None:
        # Low enough that ``-c PATH, --config PATH`` / ``-w DIR, --workspace DIR``
        # put help on the following line; wide enough for the expanded config path.
        super().__init__(prog, max_help_position=22, width=100)


def _default_config_help() -> str:
    from fj_ai.config import default_config_path

    return f"nano.yml path (default: {default_config_path()})"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fj",
        description="One-shot coding agent powered by soothe-nano",
        epilog="Queries continue the latest active thread by default.",
        formatter_class=_HelpFormatter,
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
        help=_default_config_help(),
    )
    parser.add_argument(
        "-t",
        "--thread",
        metavar="ID",
        help="Use this LangGraph thread id (pins it as active)",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List latest threads (newest first; default 20) and exit",
    )
    parser.add_argument(
        "-n",
        metavar="NUM",
        type=int,
        dest="list_limit",
        help="Number of threads to list with -l (default: 20)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Start a new active thread (alone, or with a query)",
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
        description="Interactive setup for nano.yml",
        formatter_class=_HelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help=_default_config_help(),
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


def _load_config_or_exit(args: argparse.Namespace) -> Any | int:
    from fj_ai.config import load_config

    try:
        return load_config(args.config)
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"error: failed to load config: {exc}\n")
        return 1


async def run_list_async(args: argparse.Namespace) -> int:
    """Print persisted threads, newest first."""
    from fj_ai.agent import open_sqlite_checkpointer
    from fj_ai.threads import DEFAULT_LIST_LIMIT, list_threads, write_thread_list

    config = _load_config_or_exit(args)
    if isinstance(config, int):
        return config

    limit = getattr(args, "list_limit", None)
    if limit is None:
        limit = DEFAULT_LIST_LIMIT
    elif limit < 1:
        sys.stderr.write("error: -n must be a positive integer\n")
        return 2

    try:
        async with open_sqlite_checkpointer(config) as checkpointer:
            threads = await list_threads(checkpointer, limit=limit)
            write_thread_list(threads, sys.stdout)
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    except Exception as exc:
        from fj_ai.errors import write_cli_error

        write_cli_error(exc, verbose=getattr(args, "verbose", False))
        return 1
    return 0


def run_reset_only() -> int:
    """Pin a new active thread id and print it (no agent run)."""
    from fj_ai.threads import new_thread_id, write_active_thread_id

    tid = new_thread_id()
    write_active_thread_id(tid)
    sys.stdout.write(f"{tid}\n")
    return 0


async def run_async(args: argparse.Namespace) -> int:
    if getattr(args, "list", False):
        return await run_list_async(args)

    if getattr(args, "reset", False) and not args.query_text and not args.thread:
        return run_reset_only()

    if not args.query_text:
        sys.stderr.write(USAGE)
        return 2

    # Lazy: keep ``fj __complete`` / setup free of agent import cost.
    from fj_ai.agent import build_agent, open_sqlite_checkpointer
    from fj_ai.stream import invoke_query, stream_query
    from fj_ai.threads import resolve_thread_id

    config = _load_config_or_exit(args)
    if isinstance(config, int):
        return config

    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else None

    try:
        async with open_sqlite_checkpointer(config) as checkpointer:
            thread_id = await resolve_thread_id(
                checkpointer,
                explicit=args.thread,
                reset=getattr(args, "reset", False),
            )

            agent = await build_agent(
                config,
                workspace=workspace,
                checkpointer=checkpointer,
                verbose=args.verbose,
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
        from fj_ai.errors import write_cli_error

        write_cli_error(exc, verbose=args.verbose)
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
        # Re-apply after parse so ``-v`` can enable compact console warnings.
        if getattr(args, "verbose", False):
            configure_cli_logging(verbose=True)
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
