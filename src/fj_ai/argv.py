"""Lightweight argv splitting shared by CLI and completion (no agent imports)."""

from __future__ import annotations


def split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into (option_tokens, query_tokens).

    Options are peeled from the left. After ``--``, or the first non-option
    token, the remainder is the query (preserving spaces when rejoined).
    """
    options: list[str] = []
    i = 0
    value_flags = {"-c", "--config", "-t", "--thread", "-w", "--workspace", "-n"}
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            return options, argv[i + 1 :]
        if tok in {
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
        }:
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
