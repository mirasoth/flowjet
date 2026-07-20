"""fj CLI — any characters after the command are the agent query."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from fj_ai import __version__
from fj_ai.agent import build_agent, open_sqlite_checkpointer
from fj_ai.config import default_config_path, load_config
from fj_ai.logging_setup import configure_cli_logging
from fj_ai.stream import invoke_query, stream_query

USAGE = """\
fj — coding agent CLI (soothe-nano)

Usage:
  fj <query...>
  fj [options] [--] <query...>

Examples:
  fj who is your name
  fj 修改这个文件。
  fj explain how asyncio works in this repo

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
        help=f"nano.yml path (default: {default_config_path()})",
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


def split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into (option_tokens, query_tokens).

    Options are peeled from the left. After ``--``, or the first non-option
    token, the remainder is the query (preserving spaces when rejoined).
    """
    options: list[str] = []
    i = 0
    value_flags = {"-c", "--config", "-t", "--thread", "-w", "--workspace"}
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            return options, argv[i + 1 :]
        if tok in {"-h", "--help", "-V", "--version", "--no-stream", "-v", "--verbose"}:
            options.append(tok)
            i += 1
            continue
        if tok in value_flags:
            options.append(tok)
            if i + 1 < len(argv):
                options.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue
        if (
            tok.startswith("--config=")
            or tok.startswith("--thread=")
            or tok.startswith("--workspace=")
        ):
            options.append(tok)
            i += 1
            continue
        # First non-option token starts the query (may include leading dashes).
        return options, argv[i:]
    return options, []


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args; remaining tokens become the query string."""
    raw = list(sys.argv[1:] if argv is None else argv)
    option_tokens, query_tokens = split_argv(raw)
    args = _build_parser().parse_args(option_tokens)
    args.query_text = " ".join(query_tokens).strip()
    return args


async def run_async(args: argparse.Namespace) -> int:
    if not args.query_text:
        sys.stderr.write(USAGE)
        return 2

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
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_cli_logging()
    args = parse_args(argv)
    return asyncio.run(run_async(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
