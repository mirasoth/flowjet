"""Lightweight argv splitting shared by CLI and completion (no agent imports)."""

from __future__ import annotations

from typing import Any

# Boolean short flags that may appear clustered (``-lv`` → ``-l -v``).
_BOOL_SHORTS = frozenset({"h", "V", "l", "v"})
# Short flags that consume the next argv token as a value.
_VALUE_FLAGS = frozenset({"-c", "--config", "-t", "--thread", "-w", "--workspace", "-n"})
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
        "--reset",
    }
)
_EQUALS_PREFIXES = ("--config=", "--thread=", "--workspace=")


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
    - ``-l`` is exclusive with a query, ``--reset``, ``-t``, ``-w``, ``--no-stream``
    - ``--reset`` and ``-t``/``--thread`` are mutually exclusive
    """
    listing = bool(getattr(args, "list", False))
    list_limit = getattr(args, "list_limit", None)
    reset = bool(getattr(args, "reset", False))
    thread = getattr(args, "thread", None)
    workspace = getattr(args, "workspace", None)
    no_stream = bool(getattr(args, "no_stream", False))
    query = (getattr(args, "query_text", None) or "").strip()

    if list_limit is not None and not listing:
        return "-n requires -l/--list"

    if listing:
        if query:
            return "-l/--list does not take a query (got leftover text after options)"
        if reset:
            return "-l/--list cannot be combined with --reset"
        if thread:
            return "-l/--list cannot be combined with -t/--thread"
        if workspace:
            return "-l/--list cannot be combined with -w/--workspace"
        if no_stream:
            return "-l/--list cannot be combined with --no-stream"

    if reset and thread:
        return "--reset and -t/--thread are mutually exclusive"

    return None
