"""List LangGraph threads from the sqlite checkpointer."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

_PREVIEW_LIMIT = 72


def _soothe_home() -> Path:
    """Resolve soothe home without importing soothe-nano."""
    env = os.environ.get("SOOTHE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".soothe"


def active_thread_path() -> Path:
    """Return ``~/.soothe/data/fj_active_thread`` (respects ``SOOTHE_HOME``)."""
    return _soothe_home() / "data" / "fj_active_thread"


def read_active_thread_id(path: Path | None = None) -> str | None:
    """Return the pinned active thread id, if any."""
    file = path or active_thread_path()
    try:
        text = file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def write_active_thread_id(thread_id: str, path: Path | None = None) -> None:
    """Pin ``thread_id`` as the active conversation for subsequent queries."""
    file = path or active_thread_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(thread_id.strip() + "\n", encoding="utf-8")


def new_thread_id() -> str:
    """Allocate a fresh ``fj-<uuid>`` thread id."""
    return f"fj-{uuid.uuid4()}"


@dataclass(frozen=True)
class ThreadInfo:
    """One persisted conversation thread."""

    thread_id: str
    updated_at: str | None = None
    preview: str | None = None


def simplify_timestamp(ts: str | None) -> str | None:
    """Truncate an ISO timestamp to second precision (``YYYY-MM-DD HH:MM:SS``)."""
    if not ts or not ts.strip():
        return None
    text = ts.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        if "T" in text:
            date, _, rest = text.partition("T")
            time_part = rest.split("+", 1)[0].split("-", 1)[0].split(".", 1)[0]
            if len(time_part) >= 8:
                return f"{date} {time_part[:8]}"
        return text[:19]


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return " ".join(p.strip() for p in parts if p and p.strip())
    return str(content).strip() if content is not None else ""


def _is_human_message(msg: Any) -> bool:
    msg_type = getattr(msg, "type", None)
    if msg_type == "human":
        return True
    name = type(msg).__name__
    return name in {"HumanMessage", "HumanMessageChunk"}


def preview_user_request(payload: Any, *, limit: int = _PREVIEW_LIMIT) -> str | None:
    """Extract a one-line preview of the first human message from a writes payload."""
    messages = payload if isinstance(payload, list) else [payload]
    for msg in messages:
        if not _is_human_message(msg):
            continue
        text = _content_text(getattr(msg, "content", None))
        if not text:
            continue
        text = " ".join(text.split())
        if len(text) > limit:
            return text[: limit - 1] + "…"
        return text
    return None


def _activity_sort_key(item: tuple[str, str | None, str]) -> tuple[bool, str, str]:
    """Sort key for ``reverse=True``: newest ``updated_at``, then latest checkpoint id."""
    _tid, updated_at, latest_cid = item
    return (updated_at is not None, updated_at or "", latest_cid)


async def _load_thread_activity(
    checkpointer: Any,
) -> list[tuple[str, str | None, str]]:
    """Return ``(thread_id, updated_at, latest_checkpoint_id)`` for every thread.

    ``updated_at`` comes from the latest checkpoint's ``ts`` (last activity), not
    the thread's first checkpoint (creation).
    """
    query = """
        SELECT c.thread_id, t.latest, c.type, c.checkpoint
        FROM checkpoints c
        INNER JOIN (
            SELECT thread_id, MAX(checkpoint_id) AS latest
            FROM checkpoints
            WHERE checkpoint_ns = ''
            GROUP BY thread_id
        ) t
          ON c.thread_id = t.thread_id
         AND c.checkpoint_id = t.latest
         AND c.checkpoint_ns = ''
    """
    rows: list[tuple[str, str | None, str]] = []
    async with checkpointer.conn.execute(query) as cur:
        for thread_id, latest, type_, blob in await cur.fetchall():
            updated_at: str | None = None
            try:
                checkpoint = checkpointer.serde.loads_typed((type_, blob))
                if isinstance(checkpoint, dict):
                    updated_at = simplify_timestamp(checkpoint.get("ts"))
            except Exception:
                updated_at = None
            rows.append((str(thread_id), updated_at, str(latest)))
    rows.sort(key=_activity_sort_key, reverse=True)
    return rows


async def latest_thread_id(checkpointer: Any) -> str | None:
    """Return the latest-active thread id (same ordering as ``list_threads``).

    Activity is the newest checkpoint ``ts``, not thread creation.
    """
    if checkpointer is None:
        return None
    rows = await _load_thread_activity(checkpointer)
    return rows[0][0] if rows else None


async def resolve_thread_id(
    checkpointer: Any,
    *,
    explicit: str | None = None,
    reset: bool = False,
) -> str:
    """Choose the thread for a query and pin it as active.

    Priority: ``-t`` explicit id, else ``--reset`` (new id), else pinned active
    id, else latest activity, else a new id.
    """
    if explicit:
        tid = explicit.strip()
    elif reset:
        tid = new_thread_id()
    else:
        tid = read_active_thread_id()
        if not tid:
            tid = await latest_thread_id(checkpointer)
        if not tid:
            tid = new_thread_id()
    write_active_thread_id(tid)
    return tid


async def _load_previews(checkpointer: Any, thread_ids: list[str]) -> dict[str, str | None]:
    """Map thread_id → latest human-message preview (most recent activity)."""
    if not thread_ids:
        return {}
    placeholders = ",".join("?" for _ in thread_ids)
    query = f"""
        SELECT w.thread_id, w.checkpoint_id, w.idx, w.type, w.value
        FROM writes w
        WHERE w.channel = 'messages'
          AND w.checkpoint_ns = ''
          AND w.thread_id IN ({placeholders})
        ORDER BY w.checkpoint_id DESC, w.idx DESC
    """
    out: dict[str, str | None] = {}
    async with checkpointer.conn.execute(query, thread_ids) as cur:
        rows = await cur.fetchall()
    for thread_id, _cid, _idx, type_, value in rows:
        tid = str(thread_id)
        if tid in out:
            continue
        try:
            payload = checkpointer.serde.loads_typed((type_, value))
            preview = preview_user_request(payload)
        except Exception:
            continue
        if preview:
            out[tid] = preview
    for tid in thread_ids:
        out.setdefault(tid, None)
    return out


DEFAULT_LIST_LIMIT = 20


async def list_threads(checkpointer: Any, *, limit: int = DEFAULT_LIST_LIMIT) -> list[ThreadInfo]:
    """Return threads ordered by latest activity time (newest first).

    Activity is the latest checkpoint ``ts``, not thread creation. ``limit`` caps
    how many rows are returned (default ``20``). Use a non-positive value to
    return all threads.
    """
    if checkpointer is None:
        return []

    activity = await _load_thread_activity(checkpointer)
    if limit > 0:
        activity = activity[:limit]

    ordered = [tid for tid, _ts, _cid in activity]
    updated = {tid: ts for tid, ts, _cid in activity}
    previews = await _load_previews(checkpointer, ordered)
    return [
        ThreadInfo(
            thread_id=tid,
            updated_at=updated.get(tid),
            preview=previews.get(tid),
        )
        for tid in ordered
    ]


def format_thread_list(threads: list[ThreadInfo]) -> str:
    """Format threads: ``tid  timestamp  preview`` (newest first)."""
    if not threads:
        return ""
    tid_width = max(len(t.thread_id) for t in threads)
    ts_width = max((len(t.updated_at) for t in threads if t.updated_at), default=0)
    lines: list[str] = []
    for t in threads:
        parts = [t.thread_id.ljust(tid_width)]
        if ts_width:
            parts.append((t.updated_at or "").ljust(ts_width))
        elif t.updated_at:
            parts.append(t.updated_at)
        if t.preview:
            parts.append(t.preview)
        lines.append("  ".join(parts).rstrip())
    return "\n".join(lines) + "\n"


def write_thread_list(threads: list[ThreadInfo], out: TextIO) -> None:
    out.write(format_thread_list(threads))
