"""Slim completion context — fast local probes only."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from fj_ai.argv import split_argv
from fj_ai.completion.history import read_history
from fj_ai.completion.static import SUBCOMMANDS

# Builtin fallbacks when history + LLM are empty.
DEFAULT_TASKS = (
    "summarize this repository",
    "review recent changes",
    "find TODO comments",
    "explain project architecture",
    "generate README",
)


@dataclass
class CompletionContext:
    """Inputs for local providers and the LLM prompt."""

    cwd: Path
    project_root: Path | None
    git_repo: bool
    git_branch: str | None
    staged_names: list[str] = field(default_factory=list)
    modified_names: list[str] = field(default_factory=list)
    language: str | None = None
    project_type: str | None = None
    recent_history: list[str] = field(default_factory=list)
    option_tokens: list[str] = field(default_factory=list)
    query_prefix: str = ""
    mode: str = "task"  # static | intent | task
    words: list[str] = field(default_factory=list)


def build_context(words: list[str], *, cwd: Path | None = None) -> CompletionContext:
    """Build context from shell words after the ``fj`` command name."""
    root = (cwd or Path.cwd()).resolve()
    option_tokens, query_tokens = split_argv(list(words))
    query_prefix = " ".join(query_tokens).strip()
    mode = _detect_mode(query_tokens)

    project_root = _find_project_root(root)
    git_repo, git_branch, staged, modified = _git_snapshot(root)
    language, project_type = _detect_project(project_root or root)

    return CompletionContext(
        cwd=root,
        project_root=project_root,
        git_repo=git_repo,
        git_branch=git_branch,
        staged_names=staged,
        modified_names=modified,
        language=language,
        project_type=project_type,
        recent_history=read_history(limit=40),
        option_tokens=option_tokens,
        query_prefix=query_prefix,
        mode=mode,
        words=list(words),
    )


def _detect_mode(query_tokens: list[str]) -> str:
    if not query_tokens:
        return "task"
    first = query_tokens[0]
    if first.startswith("-"):
        return "static"
    if first in SUBCOMMANDS:
        return "static"
    # Incomplete subcommand (single word, unambiguous-ish prefix).
    if len(query_tokens) == 1 and len(first) >= 3:
        if any(cmd.startswith(first) for cmd in SUBCOMMANDS):
            return "static"
    return "intent"


def _find_project_root(start: Path) -> Path | None:
    cur = start
    for _ in range(12):
        if (cur / ".git").exists() or (cur / "pyproject.toml").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _git_snapshot(cwd: Path) -> tuple[bool, str | None, list[str], list[str]]:
    if not _run_ok(["git", "rev-parse", "--is-inside-work-tree"], cwd):
        return False, None, [], []
    branch = _run_text(["git", "branch", "--show-current"], cwd) or None
    staged = _run_lines(["git", "diff", "--cached", "--name-only"], cwd)[:8]
    modified = _run_lines(["git", "diff", "--name-only"], cwd)[:8]
    return True, branch, staged, modified


def _detect_project(root: Path) -> tuple[str | None, str | None]:
    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        return "Python", "python"
    if (root / "Cargo.toml").is_file():
        return "Rust", "rust"
    if (root / "go.mod").is_file():
        return "Go", "go"
    if (root / "package.json").is_file():
        return "JavaScript", "node"
    if (root / "pom.xml").is_file() or (root / "build.gradle").is_file():
        return "Java", "java"
    return None, None


def _run_ok(cmd: list[str], cwd: Path) -> bool:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=0.15,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _run_text(cmd: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=0.15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _run_lines(cmd: list[str], cwd: Path) -> list[str]:
    text = _run_text(cmd, cwd)
    return [line for line in text.splitlines() if line.strip()]
