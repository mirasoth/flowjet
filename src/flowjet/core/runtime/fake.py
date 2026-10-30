"""Deterministic RuntimeBackend for tests and local demos."""

from __future__ import annotations

from collections.abc import AsyncIterator

from flowjet.core.events import (
    ModelInfo,
    OutputTextDelta,
    Progress,
    RunCompleted,
    RunRequest,
    RunStarted,
    RuntimeEvent,
    ToolCompleted,
    ToolStarted,
    UsageInfo,
)
from flowjet.core.ids import new_run_id, new_session_id


class FakeRuntimeBackend:
    """Echo-style backend that emits a fixed, sanitized event stream."""

    def __init__(self, models: list[str] | None = None) -> None:
        self._models = models or ["default"]

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id=m) for m in self._models]

    async def delete_run(self, run_id: str) -> None:
        return None

    async def stream_run(self, request: RunRequest) -> AsyncIterator[RuntimeEvent]:
        run_id = request.run_id or new_run_id()
        session = request.session or new_session_id()
        yield RunStarted(run_id=run_id, model=request.model, session=session)
        yield Progress(stage="Working", message="Thinking…")

        meta = request.metadata or {}
        if meta.get("emit_tools"):
            yield ToolStarted(tool="search", call_id="call_1")
            yield ToolCompleted(tool="search", ok=True, call_id="call_1", duration_ms=12)

        answer = f"Echo: {request.input_text}"
        # Chunk for streaming realism
        mid = max(1, len(answer) // 2)
        yield OutputTextDelta(delta=answer[:mid])
        yield OutputTextDelta(delta=answer[mid:])
        yield RunCompleted(
            output_text=answer,
            usage=UsageInfo(
                input_tokens=len(request.input_text.split()),
                output_tokens=len(answer.split()),
                total_tokens=len(request.input_text.split()) + len(answer.split()),
            ),
        )
