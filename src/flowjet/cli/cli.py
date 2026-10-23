"""FlowJet CLI — any characters after the command are the agent query.

Formal command: ``flowjet``. Aliases: ``fj`` (same), ``fjf`` (``-f``).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal
import sys
import traceback
from collections.abc import Coroutine
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, cast

from flowjet.cli import __version__

FORMAL_CLI = "flowjet"
CLI_ALIASES = frozenset({"fj", "fjf", FORMAL_CLI})

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI logging — stdlib only, kept here so ``fj -V`` / ``fj -h`` never pay the
# heavy ``soothe_nano`` / ``flowjet.core.agent`` import cost.
# ---------------------------------------------------------------------------

_BROWSER_USE_SETUP_LOGGING = "BROWSER_USE_SETUP_LOGGING"
_FJ_CONSOLE_HANDLER = "fj-console"
_FJ_FILE_HANDLER = "fj-file"
_LOG_FILE_ENV = "FJ_LOG_FILE"


class _CompactConsoleFormatter(logging.Formatter):
    """One-line console records; exceptions summarized on the same line.

    Full tracebacks would smash the ephemeral progress line, but dropping the
    exception entirely (the old behavior) hid the root cause even with ``-v``.
    The full stack for run failures is available via ``AgentRunError``.
    """

    def formatException(self, ei: object) -> str:  # noqa: N802 - logging API
        return ""

    def format(self, record: logging.LogRecord) -> str:
        # logger.exception sets exc_info; fold "type: message" into the record
        # message so format() stays one line without losing the cause.
        if record.exc_info:
            exc_val = record.exc_info[1]
            if exc_val is not None:
                record.msg = f"{record.getMessage()}: {type(exc_val).__name__}: {exc_val}"
            record.exc_info = None
            record.exc_text = None
        return super().format(record)


def configure_cli_logging(*, verbose: bool = False) -> None:
    """Quiet the console for one-shot CLI use.

    - Opt out of ``browser_use`` import-time root logger setup when unset.
    - Remove existing root stream handlers (stderr/stdout) so init INFO
      lines do not interleave with the agent answer.
    - Prevent ``lastResort`` traceback dumps from soothe tool failures.
    - When ``verbose``, show WARNING+ as single-line messages on stderr.
    - When ``FJ_LOG_FILE`` is set, mirror WARNING+ (with full tracebacks) to
      that rotating file for post-mortem diagnosis of silent failures.
    """
    os.environ.setdefault(_BROWSER_USE_SETUP_LOGGING, "false")
    _remove_root_console_handlers()
    root = logging.getLogger()
    if verbose:
        handler = logging.StreamHandler(sys.stderr)
        handler.set_name(_FJ_CONSOLE_HANDLER)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(_CompactConsoleFormatter("%(message)s"))
        root.addHandler(handler)
    elif not root.handlers:
        null = logging.NullHandler()
        null.set_name(_FJ_CONSOLE_HANDLER)
        root.addHandler(null)
    if root.level < logging.WARNING:
        root.setLevel(logging.WARNING)
    _attach_file_log_handler(root)


def _attach_file_log_handler(root: logging.Logger) -> None:
    """Attach the ``FJ_LOG_FILE`` rotating handler once, if requested.

    Unlike the compact console formatter, the file keeps full tracebacks, so
    ``logger.exception`` records from soothe/plugins stay diagnosable after a
    crash — including for deaths the CLI itself cannot report (SIGKILL).
    """
    if any(getattr(h, "name", None) == _FJ_FILE_HANDLER for h in root.handlers):
        return
    path = os.environ.get(_LOG_FILE_ENV, "").strip()
    if not path:
        return
    try:
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    except OSError:
        _logger.warning("FJ_LOG_FILE is not writable: %s", path)
        return
    handler.set_name(_FJ_FILE_HANDLER)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] %(message)s"))
    root.addHandler(handler)


def silence_after_plugins(*, verbose: bool = False) -> None:
    """Re-apply quieting after plugin imports (belt-and-suspenders)."""
    configure_cli_logging(verbose=verbose)


def _remove_root_console_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            continue
        if isinstance(handler, logging.FileHandler):
            continue
        if isinstance(handler, logging.StreamHandler) or isinstance(handler, logging.NullHandler):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - defensive
                pass


def resolve_cli_prog(argv0: str | None = None) -> str:
    """Return the invoked command name for help / version strings.

    Known entrypoints (``flowjet``, ``fj``, ``fjf``) are preserved.
    Unknown wrappers (``python -m …``) fall back to the formal name.
    """
    name = Path(argv0 if argv0 is not None else sys.argv[0]).name
    if name.endswith(".exe"):
        name = name[: -len(".exe")]
    if name in CLI_ALIASES:
        return name
    return FORMAL_CLI


def _cli_description(prog: str) -> str:
    alias_note = {
        FORMAL_CLI: "Aliases: fj (same), fjf (same as flowjet -f).",
        "fj": "Alias of flowjet. Also: fjf (= fj -f).",
        "fjf": "Alias of flowjet -f / fj -f (follow this project's latest thread).",
    }.get(prog, "Formal command: flowjet. Aliases: fj, fjf (= -f).")
    return (
        "FlowJet — coding agent CLI (soothe-nano)\n"
        f"\n{alias_note}\n"
        "\nPass a natural-language query after options. Remaining words are joined into\n"
        "one query string (any Unicode). Use -- to force the rest of the line into the\n"
        "query when it looks like flags."
    )


def _cli_epilog(prog: str) -> str:
    # Prefer short alias in examples when the user invoked fj/fjf.
    show = prog if prog in {"fj", "fjf"} else FORMAL_CLI
    follow = show if show == "fjf" else f"{show} -f"
    return f"""\
commands:
  {show} setup                 Interactive nano.yml setup
  {show} doctor                Diagnose runtime readiness (tool deps, providers, …)
  {show} doctor-fix            Repair Chrome/chromedriver (install/download if needed)
  {show} serve                 Run the FlowJet server (ACP + OpenAI-compatible HTTP)
  {show} completion zsh|bash   Print shell completion script

query modes:
  {show} QUERY...              Start a new thread (default)
  {follow} QUERY...           Continue this project's latest active thread
  {show} -t ID QUERY...        Continue a specific thread
  {show} -t ID                 Pin thread as active (no query)
  {show} -a QUERY...           Ask mode: answer only, no tool calls

examples:
  {show} explain this repo
  {follow} what did we decide last time?
  {show} -t abc-123 continue here
  {show} -l -n 10
  {show} doctor
  {show} doctor --deep --live-llm
  eval "$({show if show != "fjf" else "fj"} completion zsh)"

notes:
  • Formal CLI: flowjet · aliases: fj, fjf (= -f)
  • -t overrides -f when both are given; -n requires -l; -l takes no query
  • -f is per project (git root, else cwd); resume elsewhere with -t ID
  • -a/--ask disables all tools — pure Q&A, no side effects
  • Bypass mode (skip all security enforcement) is the CLI default — use -a for guardrails
  • One query per thread at a time; different threads may run concurrently
  • With -v, prints thread <id> and the project dir on stderr before the run
  • --timeout N cancels a run after N seconds (0 = no limit)
  • Exit codes: 0 ok · 1 error · 2 usage · 3 no output · 130/143 interrupted
  • Set FJ_LOG_FILE=<path> to keep warnings & errors (with tracebacks) on file
"""


# Boolean short flags that may appear clustered (``-lv`` → ``-l -v``).
_BOOL_SHORTS = frozenset({"h", "V", "l", "v", "f", "a"})
# Short flags that consume the next argv token as a value.
_VALUE_FLAGS = frozenset(
    {"-c", "--config", "-t", "--thread", "-w", "--workspace", "-n", "--timeout"}
)
_FLAG_ONLY = frozenset(
    {
        "-h",
        "--help",
        "-V",
        "--version",
        "--no-stream",
        "-v",
        "--verbose",
        "-l",
        "--list",
        "-f",
        "--follow",
        "-a",
        "--ask",
    }
)
_EQUALS_PREFIXES = ("--config=", "--thread=", "--workspace=", "--timeout=")


def _expand_short_cluster(tok: str) -> list[str] | None:
    """Expand ``-lv`` → ``['-l', '-v']`` when every letter is a known bool short.

    Returns ``None`` when ``tok`` is not a pure boolean short cluster (caller
    treats it as a query token or a normal flag).
    """
    if not tok.startswith("-") or tok.startswith("--") or len(tok) < 3 or "=" in tok:
        return None
    chars = tok[1:]
    if not chars.isalpha() or not all(c in _BOOL_SHORTS for c in chars):
        return None
    return [f"-{c}" for c in chars]


def split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into (option_tokens, query_tokens).

    Options are peeled from the left. After ``--``, or the first non-option
    token, the remainder is the query (preserving spaces when rejoined).

    Boolean short flags may be clustered (``-lv`` → ``-l -v``). Clusters that
    mix unknown letters stay in the query (so ``-weird`` is still a query).
    """
    options: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            return options, argv[i + 1 :]
        expanded = _expand_short_cluster(tok)
        if expanded is not None:
            options.extend(expanded)
            i += 1
            continue
        if tok in _FLAG_ONLY:
            options.append(tok)
            i += 1
            continue
        if tok in _VALUE_FLAGS:
            options.append(tok)
            if i + 1 < len(argv):
                options.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue
        if any(tok.startswith(p) for p in _EQUALS_PREFIXES):
            options.append(tok)
            i += 1
            continue
        # First non-option token starts the query (may include leading dashes).
        return options, argv[i:]
    return options, []


def validate_arg_composition(args: Any) -> str | None:
    """Return an error message when flag combinations are invalid, else ``None``.

    Rules:
    - ``-n`` requires ``-l``/``--list``
    - ``-l`` is exclusive with a query, ``-f``, ``-t``, ``-w``, ``--no-stream``, ``--ask``
    - ``-t``/``--thread`` overrides ``-f``/``--follow`` when both are given
    - ``--timeout`` must be >= 0 (0 = no limit)
    """
    listing = bool(getattr(args, "list", False))
    list_limit = getattr(args, "list_limit", None)
    follow = bool(getattr(args, "follow", False))
    thread = getattr(args, "thread", None)
    workspace = getattr(args, "workspace", None)
    no_stream = bool(getattr(args, "no_stream", False))
    ask = bool(getattr(args, "ask", False))
    query = (getattr(args, "query_text", None) or "").strip()

    if list_limit is not None and not listing:
        return "-n requires -l/--list"

    timeout = getattr(args, "timeout", None)
    if timeout is not None and timeout < 0:
        return "--timeout must be >= 0 (0 = no limit)"

    if listing:
        if query:
            return "-l/--list does not take a query (got leftover text after options)"
        if follow:
            return "-l/--list cannot be combined with -f/--follow"
        if thread:
            return "-l/--list cannot be combined with -t/--thread"
        if workspace:
            return "-l/--list cannot be combined with -w/--workspace"
        if no_stream:
            return "-l/--list cannot be combined with --no-stream"
        if ask:
            return "-l/--list cannot be combined with -a/--ask"

    return None


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Preserve paragraph breaks; align option help cleanly."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=26, width=92)

    def _format_action(self, action: argparse.Action) -> str:  # type: ignore[override]
        # Resolve lazy help strings only when help is actually rendered, so
        # ``-V`` never pays for the import behind ``_default_config_help``.
        if isinstance(action.help, _LazyHelp):
            action.help = str(action.help)
        return super()._format_action(action)


def _default_config_help() -> str:
    from flowjet.home import default_config_path

    return f"Alternate nano.yml (default: {default_config_path()})"


class _LazyHelp:
    """Resolve a help-string callable only when argparse reads it.

    ``-V`` / ``-h``-without-our-flag paths never touch the help text, so the
    heavy import behind ``_default_config_help`` stays deferred until a flag
    that actually shows help (``-h``) or errors is invoked.
    """

    __slots__ = ("_factory", "_cached")

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._cached: str | None = None

    def __str__(self) -> str:
        if self._cached is None:
            self._cached = self._factory()
        return self._cached


def _build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    cli_prog = prog or resolve_cli_prog()
    parser = argparse.ArgumentParser(
        prog=cli_prog,
        description=_cli_description(cli_prog),
        epilog=_cli_epilog(cli_prog),
        formatter_class=_HelpFormatter,
        add_help=True,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"{cli_prog} {__version__}",
    )

    thread = parser.add_argument_group("thread")
    thread.add_argument(
        "-t",
        "--thread",
        metavar="ID",
        help="Thread id (-t alone: pin active; with query: continue it; overrides -f)",
    )
    thread.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Continue the latest active thread in this project directory",
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
    output.add_argument(
        "-a",
        "--ask",
        action="store_true",
        help="Ask mode: answer the query with no tools (pure Q&A)",
    )

    run = parser.add_argument_group("run")
    run.add_argument(
        "--timeout",
        metavar="SECONDS",
        type=float,
        help="Cancel the run after N seconds (0 = no limit)",
    )

    paths = parser.add_argument_group("paths")
    paths.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        # Lazy help keeps the heavy default-config import off -V / normal runs.
        help=cast("str", _LazyHelp(_default_config_help)),
    )
    paths.add_argument(
        "-w",
        "--workspace",
        metavar="DIR",
        help="Workspace root for tools (default: cwd)",
    )
    return parser


def cli_help_text(prog: str | None = None) -> str:
    """Full help text (same as ``flowjet -h`` / ``fj -h``)."""
    return _build_parser(prog).format_help()


def _build_setup_parser(prog: str | None = None) -> argparse.ArgumentParser:
    cli_prog = prog or resolve_cli_prog()
    parser = argparse.ArgumentParser(
        prog=f"{cli_prog} setup",
        description="Interactive setup for nano.yml",
        formatter_class=_HelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        # Lazy help keeps the heavy default-config import off -V / normal runs.
        help=cast("str", _LazyHelp(_default_config_help)),
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
    if raw and raw[0] == "doctor":
        ns = argparse.Namespace(query_text="", doctor_argv=raw[1:])
        return _namespace_with_command(ns, "doctor")
    if raw and raw[0] == "doctor-fix":
        ns = argparse.Namespace(query_text="", doctor_fix_argv=raw[1:])
        return _namespace_with_command(ns, "doctor-fix")
    if raw and raw[0] == "serve":
        ns = argparse.Namespace(query_text="", serve_argv=raw[1:])
        return _namespace_with_command(ns, "serve")
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
    from flowjet.cli.agent import load_config

    try:
        return load_config(args.config)
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"error: failed to load config: {exc}\n")
        if getattr(args, "verbose", False):
            sys.stderr.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        return 1


async def run_list_async(args: argparse.Namespace) -> int:
    """Print persisted threads, newest first."""
    from flowjet.cli.agent import open_sqlite_checkpointer
    from flowjet.cli.threads import DEFAULT_LIST_LIMIT, list_threads, write_thread_list

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
        from flowjet.cli.stream import write_cli_error

        write_cli_error(exc, verbose=getattr(args, "verbose", False))
        return 1
    return 0


def run_pin_thread(thread_id: str) -> int:
    """Pin ``thread_id`` as active and print it (no agent run)."""
    from flowjet.cli.threads import write_active_thread_id

    tid = thread_id.strip()
    if not tid:
        sys.stderr.write("error: -t/--thread requires a non-empty id\n")
        return 2
    write_active_thread_id(tid)
    sys.stdout.write(f"{tid}\n")
    return 0


async def _detect_pending_interrupt(agent: Any, thread_id: str) -> Any:
    """Return the pending ``ask_user`` interrupt value, or ``None``.

    Thin wrapper over the shared bridge helper
    (:func:`flowjet.core.bridges.nano.interrupts.detect_pending_ask_user`) so
    the CLI and the server surfaces apply the exact same probe. When an
    ``ask_user`` interrupt is pending, its ``value`` carries the question
    specs; the run resumes by feeding the user's answer to
    ``Command(resume=...)``.
    """
    from flowjet.core.bridges.nano.interrupts import detect_pending_ask_user

    return await detect_pending_ask_user(agent, {"configurable": {"thread_id": thread_id}})


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
    from flowjet.cli.agent import build_agent, open_sqlite_checkpointer
    from flowjet.cli.stream import invoke_query, stream_query
    from flowjet.cli.threads import (
        ConcurrentSessionError,
        hold_thread_lock,
        resolve_thread_id,
        resolve_workdir,
    )

    config = _load_config_or_exit(args)
    if isinstance(config, int):
        return config

    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else None
    # ``--timeout 0`` means no limit (same as omitting the flag).
    timeout_raw = getattr(args, "timeout", None)
    timeout_s = float(timeout_raw) if timeout_raw else None

    try:
        async with open_sqlite_checkpointer(config) as checkpointer:
            thread_id = await resolve_thread_id(
                checkpointer,
                explicit=args.thread,
                follow=getattr(args, "follow", False),
            )
            with hold_thread_lock(thread_id):
                if args.verbose:
                    sys.stderr.write(f"thread {thread_id} · {resolve_workdir()}\n")
                    sys.stderr.flush()

                agent = await build_agent(
                    config,
                    workspace=workspace,
                    checkpointer=checkpointer,
                    verbose=args.verbose,
                    ask_mode=getattr(args, "ask", False),
                )
                # If the thread paused on an ``ask_user`` interrupt, the user's
                # query text is their answer — resume the run instead of
                # starting a new turn. ``fjf`` (follow) hits this path when the
                # previous run ended on a question.
                resume_value: Any = None
                pending = await _detect_pending_interrupt(agent, thread_id)
                if pending is not None:
                    from flowjet.cli.stream import format_questions_block

                    questions = pending.get("questions") or ()
                    if isinstance(questions, list):
                        questions = tuple(q for q in questions if isinstance(q, dict))
                    else:
                        questions = ()
                    # Print the questions so the user sees what they're answering.
                    if questions:
                        sys.stdout.write(format_questions_block(questions, thread_id))
                        sys.stdout.flush()
                    resume_value = {"answers": [args.query_text]}
                if args.no_stream:
                    result = await invoke_query(
                        agent,
                        args.query_text,
                        thread_id=thread_id,
                        resume_value=resume_value,
                        timeout_s=timeout_s,
                    )
                else:
                    result = await stream_query(
                        agent,
                        args.query_text,
                        thread_id=thread_id,
                        show_tool_calls=args.verbose,
                        resume_value=resume_value,
                        timeout_s=timeout_s,
                    )
    except ConcurrentSessionError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    except asyncio.CancelledError:
        sig = _interrupt_signal
        if sig is not None:
            name = signal.Signals(sig).name
            sys.stderr.write(f"\ninterrupted by {name} (signal {sig})\n")
            return 128 + sig
        sys.stderr.write("error: run cancelled\n")
        return 130
    except BrokenPipeError:
        # Our stdout consumer (e.g. ``fj q | head``) closed early. The final
        # flush guard in ``main`` silences the shutdown-time noise.
        sys.stderr.write("error: output pipe closed\n")
        return 141
    except SystemExit as exc:
        # A plugin/tool called sys.exit() mid-run; without this the process
        # would exit with no message at all.
        sys.stderr.write(
            f"error: unexpected exit({exc.code}) raised during the run (plugin/tool called sys.exit)\n"
        )
        return 1
    except Exception as exc:
        from flowjet.cli.stream import write_cli_error

        write_cli_error(exc, verbose=args.verbose)
        return 1

    try:
        from flowjet.cli.completion.context import append_history

        append_history(args.query_text)
    except Exception:
        pass
    if not result:
        # Completed but produced no answer text (a warning is already on
        # stderr) — scripts need a distinct, detectable exit code.
        return 3
    return 0


# Seconds a stray background task gets to honour cancellation before the loop is
# closed anyway.
_TEARDOWN_GRACE_S = 3.0

# Signal (SIGTERM/SIGHUP) that cancelled the current run, if any. Module-level
# because the loop-installed callback and `run_async` share the main thread.
_interrupt_signal: int | None = None


def _on_interrupt_signal(sig: int, task: asyncio.Task[int]) -> None:
    # Convert SIGTERM/SIGHUP into a graceful task cancel (recorded for the exit code).
    global _interrupt_signal
    if _interrupt_signal is None:
        _interrupt_signal = int(sig)
    if not task.done():
        task.cancel()


def _install_signal_cancellation(
    loop: asyncio.AbstractEventLoop,
    task: asyncio.Task[int],
) -> list[tuple[int, Any]]:
    # Route SIGTERM/SIGHUP through the loop so the run unwinds cleanly.
    #
    # Without this the default disposition kills the process instantly — no
    # cleanup, no message (the "no message and exit" symptom). Platforms
    # without add_signal_handler (Windows) or non-main-thread callers keep
    # the default behaviour.
    installed: list[tuple[int, Any]] = []
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        previous = signal.getsignal(sig)
        try:
            loop.add_signal_handler(sig, _on_interrupt_signal, sig, task)
        except (NotImplementedError, RuntimeError, ValueError, OSError):
            continue
        installed.append((int(sig), previous))
    return installed


def _remove_signal_cancellation(
    loop: asyncio.AbstractEventLoop,
    installed: list[tuple[int, Any]],
) -> None:
    for sig, previous in installed:
        with contextlib.suppress(Exception, asyncio.CancelledError):
            loop.remove_signal_handler(signal.Signals(sig))
        if previous not in (signal.SIG_DFL, None):
            with contextlib.suppress(Exception, asyncio.CancelledError):
                signal.signal(signal.Signals(sig), previous)  # type: ignore[arg-type]


async def _cancel_stray_tasks(loop: asyncio.AbstractEventLoop, grace: float) -> None:
    """Cancel every task but this one, and close async generators, within ``grace``.

    Runtimes reached through tools may ignore cancellation: ``bubus`` event buses
    behind ``browser_use`` catch ``CancelledError`` and re-arm a 0.1s poll loop,
    so waiting on them without a deadline never returns.
    """
    stray = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    if stray:
        for task in stray:
            task.cancel()
        await asyncio.wait(stray, timeout=grace)
    with contextlib.suppress(Exception):
        await asyncio.wait_for(loop.shutdown_asyncgens(), timeout=grace)


def run_one_shot(coro: Coroutine[Any, Any, int], *, grace: float = _TEARDOWN_GRACE_S) -> int:
    """Run ``coro`` on a fresh loop, then tear that loop down with a deadline.

    ``asyncio.run`` cancels leftover tasks and gathers them with no timeout, so
    one task that swallows ``CancelledError`` pins the process after the answer
    has already been printed. ``loop.close()`` is also where libraries install
    their own cleanup hooks, so it runs whether or not the strays went quietly.

    SIGTERM/SIGHUP cancel the main task instead of killing the process, so the
    run unwinds with a visible message and a conventional 128+signal exit code.
    """
    global _interrupt_signal
    _interrupt_signal = None
    loop = asyncio.new_event_loop()
    installed: list[tuple[int, Any]] = []
    try:
        asyncio.set_event_loop(loop)
        task = loop.create_task(coro, name="fj-run")
        installed = _install_signal_cancellation(loop, task)
        return loop.run_until_complete(task)
    finally:
        _remove_signal_cancellation(loop, installed)
        # CancelledError is a BaseException — a stray re-cancel during teardown
        # must not mask the real result/exception.
        with contextlib.suppress(Exception, asyncio.CancelledError):
            loop.run_until_complete(_cancel_stray_tasks(loop, grace))
        asyncio.set_event_loop(None)
        loop.close()


_FOLLOW_SUBCOMMANDS = frozenset(
    {"setup", "doctor", "doctor-fix", "serve", "completion", "__complete"}
)


def _inject_follow(argv: list[str]) -> list[str]:
    """Prepend ``--follow`` unless argv already sets it or is a subcommand."""
    if argv and argv[0] in _FOLLOW_SUBCOMMANDS:
        return argv
    if "-f" in argv or "--follow" in argv:
        return argv
    return ["--follow", *argv]


def main_follow(argv: list[str] | None = None) -> int:
    """``fjf`` entry point — alias of ``flowjet -f`` / ``fj -f``."""
    raw = list(sys.argv[1:] if argv is None else argv)
    return main(_inject_follow(raw))


def _handle_broken_pipe() -> int:
    """Silence the shutdown flush noise after our stdout consumer closed early."""
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except (OSError, ValueError, AttributeError):  # pragma: no cover - platform
        pass
    return 141  # 128 + SIGPIPE


def main(argv: list[str] | None = None) -> int:
    # Silence noisy third-party warnings (requests version-mismatch,
    # LangChain beta-API) before any heavy import pulls them in.
    from flowjet.core._warnings import suppress_known_warnings

    suppress_known_warnings()
    try:
        # Parse first so ``-V`` / ``-h`` / ``--help`` exit before we touch the
        # logging stack (and the heavy ``flowjet.cli.agent`` import it used to
        # drag in). Version/help must stay instant.
        args = parse_args(argv)
        configure_cli_logging()
        # Re-apply after parse so ``-v`` can enable compact console warnings.
        if getattr(args, "verbose", False):
            configure_cli_logging(verbose=True)
        # Keep interactive setup / doctor / completion off the event loop so Ctrl+C exits cleanly.
        if args.command == "setup":
            from flowjet.cli.setup_cmd import run_setup

            result = run_setup(getattr(args, "config", None))
        elif args.command == "doctor":
            from flowjet.cli.doctor_cmd import run_doctor

            result = run_doctor(getattr(args, "doctor_argv", []))
        elif args.command == "doctor-fix":
            from flowjet.cli.doctor_fix_cmd import run_doctor_fix

            result = run_doctor_fix(getattr(args, "doctor_fix_argv", []))
        elif args.command == "__complete":
            from flowjet.cli.completion import run_complete

            result = run_complete(getattr(args, "complete_argv", []))
        elif args.command == "serve":
            # Lazy: the server extra (fastapi/uvicorn/acp) must never be an
            # import-time dependency of the CLI.
            from flowjet.cli.serve_cmd import run_serve

            result = run_serve(getattr(args, "serve_argv", []))
        elif args.command == "completion":
            from flowjet.cli.completion import run_completion_script

            result = run_completion_script(getattr(args, "completion_argv", []))
        else:
            result = run_one_shot(run_async(args))
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130
    except BrokenPipeError:
        return _handle_broken_pipe()
    try:
        # Flush before returning: a closed consumer would otherwise trigger
        # "Exception ignored" noise during interpreter shutdown.
        sys.stdout.flush()
    except BrokenPipeError:
        return _handle_broken_pipe()
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
