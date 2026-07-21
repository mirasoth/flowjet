"""Persistent recent-query history for completion personalization."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_MAX_ENTRIES = 200


def _soothe_home() -> Path:
    """Resolve soothe home without importing soothe-nano (keeps Tab fast)."""
    env = os.environ.get("SOOTHE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".soothe"


def history_path() -> Path:
    """Return ``~/.soothe/data/fj_completion_history.jsonl`` (respects ``SOOTHE_HOME``)."""
    return _soothe_home() / "data" / "fj_completion_history.jsonl"


def read_history(path: Path | None = None, *, limit: int = 50) -> list[str]:
    """Return recent queries, newest first (deduped, case-sensitive keep-first)."""
    file = path or history_path()
    if not file.is_file():
        return []
    rows: list[str] = []
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            query = line
        else:
            if isinstance(payload, dict):
                query = str(payload.get("query", "")).strip()
            elif isinstance(payload, str):
                query = payload.strip()
            else:
                continue
        if query:
            rows.append(query)
    # Newest at end of file → reverse, then dedupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for query in reversed(rows):
        key = query.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(query)
        if len(out) >= limit:
            break
    return out


def append_history(
    query: str,
    path: Path | None = None,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
) -> None:
    """Append a successful query; trim file when it grows past ``max_entries``."""
    text = query.strip()
    if not text:
        return
    file = path or history_path()
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"query": text}, ensure_ascii=False) + "\n")
    except OSError:
        return
    _trim_history(file, max_entries=max_entries)


def _trim_history(file: Path, *, max_entries: int) -> None:
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= max_entries:
        return
    keep = lines[-max_entries:]
    try:
        file.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except OSError:
        return
