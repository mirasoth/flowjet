"""List LangGraph threads from the sqlite checkpointer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, TextIO

_PREVIEW_LIMIT = 72


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


async def latest_thread_id(checkpointer: Any) -> str | None:
    """Return the most recently updated thread id, or ``None`` if none exist."""
    if checkpointer is None:
        return None

    query = """
        SELECT thread_id
        FROM checkpoints
        WHERE checkpoint_ns = ''
        GROUP BY thread_id
        ORDER BY MAX(checkpoint_id) DESC
        LIMIT 1
    """
    async with checkpointer.conn.execute(query) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return str(row[0])


async def _load_updated_at(checkpointer: Any, thread_ids: list[str]) -> dict[str, str | None]:
    """Map thread_id → simplified timestamp from each thread's latest checkpoint."""
    if not thread_ids:
        return {}
    placeholders = ",".join("?" for _ in thread_ids)
    query = f"""
        SELECT c.thread_id, t.latest, c.type, c.checkpoint
        FROM checkpoints c
        INNER JOIN (
            SELECT thread_id, MAX(checkpoint_id) AS latest
            FROM checkpoints
            WHERE checkpoint_ns = '' AND thread_id IN ({placeholders})
            GROUP BY thread_id
        ) t
          ON c.thread_id = t.thread_id
         AND c.checkpoint_id = t.latest
         AND c.checkpoint_ns = ''
    """
    out: dict[str, str | None] = {}
    async with checkpointer.conn.execute(query, thread_ids) as cur:
        rows = await cur.fetchall()
    for thread_id, _latest, type_, blob in rows:
        updated_at: str | None = None
        try:
            checkpoint = checkpointer.serde.loads_typed((type_, blob))
            if isinstance(checkpoint, dict):
                updated_at = simplify_timestamp(checkpoint.get("ts"))
        except Exception:
            updated_at = None
        out[str(thread_id)] = updated_at
    return out


async def _load_previews(checkpointer: Any, thread_ids: list[str]) -> dict[str, str | None]:
    """Map thread_id → first human-message preview from earliest messages write."""
    if not thread_ids:
        return {}
    placeholders = ",".join("?" for _ in thread_ids)
    query = f"""
        SELECT w.thread_id, w.checkpoint_id, w.idx, w.type, w.value
        FROM writes w
        INNER JOIN (
            SELECT thread_id, MIN(checkpoint_id) AS first_cid
            FROM writes
            WHERE channel = 'messages'
              AND checkpoint_ns = ''
              AND thread_id IN ({placeholders})
            GROUP BY thread_id
        ) f
          ON w.thread_id = f.thread_id
         AND w.checkpoint_id = f.first_cid
         AND w.channel = 'messages'
         AND w.checkpoint_ns = ''
        ORDER BY w.thread_id, w.idx
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
            out[tid] = preview_user_request(payload)
        except Exception:
            out[tid] = None
    return out


DEFAULT_LIST_LIMIT = 20


async def list_threads(checkpointer: Any, *, limit: int = DEFAULT_LIST_LIMIT) -> list[ThreadInfo]:
    """Return threads ordered by latest activity (newest first).

    ``limit`` caps how many rows are returned (default ``20``). Use a non-positive
    value to return all threads.
    """
    if checkpointer is None:
        return []

    order_query = """
        SELECT thread_id
        FROM checkpoints
        WHERE checkpoint_ns = ''
        GROUP BY thread_id
        ORDER BY MAX(checkpoint_id) DESC
    """
    params: tuple[Any, ...] = ()
    if limit > 0:
        order_query += "\n        LIMIT ?"
        params = (limit,)

    async with checkpointer.conn.execute(order_query, params) as cur:
        ordered = [str(row[0]) for row in await cur.fetchall()]

    updated = await _load_updated_at(checkpointer, ordered)
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
