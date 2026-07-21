"""fj CLI — any characters after the command are the agent query."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from fj_ai import __version__
from fj_ai.argv import split_argv, validate_arg_composition
from fj_ai.logging_setup import configure_cli_logging

_CLI_DESCRIPTION = """\
fj — coding agent CLI (soothe-nano)

Pass a natural-language query after options. Remaining words are joined into
one query string (any Unicode). Use -- to force the rest of the line into the
query when it looks like flags."""

_CLI_EPILOG = """\
commands:
  fj setup                 Interactive nano.yml setup
  fj completion zsh|bash   Print shell completion script

query modes:
  fj QUERY...              Start a new thread (default)
  fj -f QUERY...           Continue the latest active thread
  fj -t ID QUERY...        Continue a specific thread
  fj -t ID                 Pin thread as active (no query)

examples:
  fj explain this repo
  fj -f what did we decide last time?
  fj -t fj-abc-123 continue here
  fj -l -n 10
  eval "$(fj completion zsh)"

notes:
  • -f and -t are mutually exclusive; -n requires -l; -l takes no query
  • One query per thread at a time; different threads may run concurrently
  • With -v, prints thread <id> on stderr before the run
"""


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Preserve paragraph breaks; align option help cleanly."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=26, width=92)


def _default_config_help() -> str:
    from fj_ai.config import default_config_path

    return f"Alternate nano.yml (default: {default_config_path()})"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fj",
        description=_CLI_DESCRIPTION,
        epilog=_CLI_EPILOG,
        formatter_class=_HelpFormatter,
        add_help=True,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"fj {__version__}",
    )

    thread = parser.add_argument_group("thread")
    thread.add_argument(
        "-t",
        "--thread",
        metavar="ID",
        help="Thread id (-t alone: pin active; with query: continue it)",
    )
    thread.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Continue the latest active thread",
    )
    thread.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List threads, newest first (default: 20), then exit",
    )
    thread.add_argument(
        "-n",
        metavar="NUM",
        type=int,
        dest="list_limit",
        help="With -l: max threads to show (0 = all)",
    )

    output = parser.add_argument_group("output")
    output.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Mirror tool calls and custom events on stderr",
    )
    output.add_argument(
        "--no-stream",
        action="store_true",
        help="Wait for the full answer instead of streaming tokens",
    )

    paths = parser.add_argument_group("paths")
    paths.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help=_default_config_help(),
    )
    paths.add_argument(
        "-w",
        "--workspace",
        metavar="DIR",
        help="Workspace root for tools (default: cwd)",
    )
    return parser


def cli_help_text() -> str:
    """Full ``fj`` help text (same as ``fj -h``)."""
    return _build_parser().format_help()


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
    elif limit < 0:
        sys.stderr.write("error: -n must be >= 0 (0 = list all)\n")
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


def run_pin_thread(thread_id: str) -> int:
    """Pin ``thread_id`` as active and print it (no agent run)."""
    from fj_ai.threads import write_active_thread_id

    tid = thread_id.strip()
    if not tid:
        sys.stderr.write("error: -t/--thread requires a non-empty id\n")
        return 2
    write_active_thread_id(tid)
    sys.stdout.write(f"{tid}\n")
    return 0


async def run_async(args: argparse.Namespace) -> int:
    conflict = validate_arg_composition(args)
    if conflict:
        sys.stderr.write(f"error: {conflict}\n")
        return 2

    if getattr(args, "list", False):
        return await run_list_async(args)

    if args.thread and not args.query_text:
        return run_pin_thread(args.thread)

    if not args.query_text:
        sys.stderr.write(cli_help_text())
        return 2

    # Lazy: keep ``fj __complete`` / setup free of agent import cost.
    from fj_ai.agent import build_agent, open_sqlite_checkpointer
    from fj_ai.stream import invoke_query, stream_query
    from fj_ai.threads import ConcurrentSessionError, hold_thread_lock, resolve_thread_id

    config = _load_config_or_exit(args)
    if isinstance(config, int):
        return config

    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else None

    try:
        async with open_sqlite_checkpointer(config) as checkpointer:
            thread_id = await resolve_thread_id(
                checkpointer,
                explicit=args.thread,
                follow=getattr(args, "follow", False),
            )
            with hold_thread_lock(thread_id):
                if args.verbose:
                    sys.stderr.write(f"thread {thread_id}\n")
                    sys.stderr.flush()

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
    except ConcurrentSessionError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
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
