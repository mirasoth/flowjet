"""Request-carried bindings for isolated pool execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class IsolatedRunRequest:
    """All parameters needed to run one turn on a pool worker."""

    run_id: str
    session: str
    input_text: str
    model: str
    workspace: Path
    thread_id: str | None = None
    metadata: dict[str, Any] | None = None
    request_id: str | None = None
    # When set, the run resumes a paused graph (``ask_user`` interrupt) with
    # this value via ``Command(resume=...)`` instead of starting a new turn
    # from ``input_text``. ``None`` lets the bridge auto-detect a pending
    # ``ask_user`` interrupt on the thread.
    resume_value: Any = None

    def effective_thread_id(self) -> str:
        return self.thread_id or self.session
