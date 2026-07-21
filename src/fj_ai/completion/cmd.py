"""CLI entrypoints for ``fj __complete`` and ``fj completion``."""

from __future__ import annotations

import argparse
import importlib.resources
import sys
from typing import Any


def _split_complete_argv(raw: list[str]) -> tuple[list[str], list[str]]:
    """Split ``__complete`` argv into (our_flags, shell_words)."""
    if "--" in raw:
        idx = raw.index("--")
        return raw[:idx], raw[idx + 1 :]
    # No separator: treat known flags first, remainder as words.
    flags: list[str] = []
    i = 0
    while i < len(raw):
        tok = raw[i]
        if tok in {"-h", "--help", "--no-llm"}:
            flags.append(tok)
            i += 1
            continue
        if tok in {"-c", "--config", "--timeout"}:
            flags.append(tok)
            if i + 1 < len(raw):
                flags.append(raw[i + 1])
                i += 2
            else:
                i += 1
            continue
        if tok.startswith("--config=") or tok.startswith("--timeout="):
            flags.append(tok)
            i += 1
            continue
        break
    return flags, raw[i:]


def run_complete(argv: list[str] | None = None) -> int:
    """Hidden shell protocol: print one candidate per stdout line."""
    parser = argparse.ArgumentParser(prog="fj __complete", add_help=True)
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="nano.yml path (default: ~/.soothe/config/nano.yml)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip fast-model call (local candidates only)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0.25,
        metavar="SEC",
        help="LLM timeout in seconds (default: 0.25)",
    )
    raw = list(sys.argv[1:] if argv is None else argv)
    flag_tokens, words = _split_complete_argv(raw)
    args = parser.parse_args(flag_tokens)

    config: Any | None = None
    if not args.no_llm:
        try:
            from fj_ai.config import load_config

            config = load_config(args.config)
        except Exception:
            config = None

    from fj_ai.completion.engine import complete

    try:
        candidates = complete(
            list(words),
            config=config,
            llm_timeout_s=float(args.timeout),
            use_llm=not args.no_llm and config is not None,
        )
    except Exception:
        candidates = []

    for item in candidates:
        sys.stdout.write(item.replace("\n", " ").strip() + "\n")
    return 0


def run_completion_script(argv: list[str] | None = None) -> int:
    """Print shell install script: ``fj completion zsh|bash``."""
    parser = argparse.ArgumentParser(
        prog="fj completion",
        description="Print shell completion script to stdout",
    )
    parser.add_argument(
        "shell",
        choices=("zsh", "bash"),
        help="Shell type",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    name = "_fj.zsh" if args.shell == "zsh" else "fj.bash"
    try:
        script = importlib.resources.files("fj_ai.shell").joinpath(name).read_text(encoding="utf-8")
    except Exception as exc:
        sys.stderr.write(f"error: completion script unavailable: {exc}\n")
        return 1
    sys.stdout.write(script)
    if not script.endswith("\n"):
        sys.stdout.write("\n")
    return 0
