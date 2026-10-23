"""Pending ``ask_user`` interrupt detection for graph threads.

One helper shared by the CLI (``fj``/``fjf``) and the server surfaces: read the
LangGraph thread snapshot and return the pending ``ask_user`` interrupt value,
if any. A pending interrupt means the previous turn on this thread ended on a
clarification question — the next input text is the *answer*, to be delivered
via ``Command(resume=...)`` rather than a fresh ``HumanMessage`` turn.

The check is stateless (it reads the checkpointer, not an in-memory flag), so
it stays correct across process restarts and pool-worker recycling — provided
the agent was built with a persistent checkpointer. Without one,
``aget_state`` soft-fails to ``None`` and callers simply start a new turn
(the pre-fix server behavior).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _snapshot_interrupts(snapshot: Any) -> list[Any]:
    """Collect interrupt entries from a LangGraph snapshot.

    Root-level ``snapshot.interrupts`` is the common shape; some snapshots
    nest them under per-task state (``snapshot.tasks[*].interrupts``).
    """
    interrupts = list(getattr(snapshot, "interrupts", None) or ())
    if interrupts:
        return interrupts
    for task in getattr(snapshot, "tasks", None) or ():
        task_interrupts = list(getattr(task, "interrupts", None) or ())
        if task_interrupts:
            return task_interrupts
    return []


async def detect_pending_ask_user(
    agent: Any,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the pending ``ask_user`` interrupt value on ``config``'s thread.

    ``config`` is the runnable config (``{"configurable": {...}}``) the run
    itself would use — it must carry the ``thread_id`` (and, on dual-mode
    agents, the ``interaction_mode``) so the state read routes to the same
    graph the turn will run on.

    Returns ``None`` when the agent cannot read graph state (no checkpointer),
    the snapshot lookup fails, or no ``ask_user`` interrupt is pending. Never
    raises: a failed probe degrades to "start a new turn".
    """
    get_state = getattr(agent, "aget_state", None)
    if not callable(get_state):
        return None
    try:
        snapshot = await get_state(config)
    except Exception as exc:  # noqa: BLE001 - probe must never break the turn
        # Not fatal — but explain why a pending question may be missed and a
        # new turn started instead of resuming.
        logger.warning("thread snapshot check failed; starting a new turn: %s", exc)
        return None
    if snapshot is None:
        return None
    for entry in _snapshot_interrupts(snapshot):
        value = getattr(entry, "value", None)
        if isinstance(value, dict) and value.get("type") == "ask_user":
            return value
    return None


__all__ = ["detect_pending_ask_user"]
