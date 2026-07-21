"""Static / traditional completions for flags and subcommands."""

from __future__ import annotations

SUBCOMMANDS = ("setup", "completion")

FLAGS = (
    "-h",
    "--help",
    "-V",
    "--version",
    "-c",
    "--config",
    "-t",
    "--thread",
    "-l",
    "--list",
    "-n",
    "--reset",
    "-w",
    "--workspace",
    "--no-stream",
    "-v",
    "--verbose",
)

COMPLETION_SHELLS = ("zsh", "bash")


def is_static_prefix(prefix: str) -> bool:
    """True when the incomplete token looks like a flag or known subcommand."""
    text = prefix.strip()
    if not text:
        return False
    if text.startswith("-"):
        return True
    first = text.split()[0]
    return any(cmd.startswith(first) for cmd in SUBCOMMANDS)


def static_candidates(prefix: str) -> list[str]:
    """Return flag/subcommand completions matching ``prefix``."""
    text = prefix.strip()
    if not text:
        return []

    if text.startswith("-"):
        return [flag for flag in FLAGS if flag.startswith(text)]

    parts = text.split()
    first = parts[0]
    if first == "completion" or "completion".startswith(first):
        if first == "completion" and len(parts) >= 2:
            shell_prefix = parts[1]
            return [s for s in COMPLETION_SHELLS if s.startswith(shell_prefix)]
        if first == "completion":
            return list(COMPLETION_SHELLS)
        return ["completion"] if "completion".startswith(first) else []

    return [cmd for cmd in SUBCOMMANDS if cmd.startswith(first)]
