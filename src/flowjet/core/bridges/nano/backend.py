"""NanoRuntimeBackend — in-process nano bridge (tests / DI) and factory helpers.

Production app wiring uses ``IsolatingRuntimeBackend`` + ``NanoAgentAdapter``.
This class remains for unit tests that inject a stub agent without a thread pool.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from flowjet.core.bridges.base import IsolatingBackendBuilder
from flowjet.core.bridges.nano.adapter import NanoAgentAdapter
from flowjet.core.bridges.nano.mapping import iter_nano_runtime_events
from flowjet.core.events import ModelInfo, RunRequest, RuntimeEvent
from flowjet.core.modes import InteractionMode


class NanoRuntimeBackend:
    """RuntimeBackend backed by soothe-nano, in-process (tests / DI)."""

    def __init__(
        self,
        models: list[str] | None = None,
        agent: Any | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self._models = models or ["default"]
        self._agent = agent
        self._config_path = Path(config_path).expanduser() if config_path else None

    def _ensure_agent(self) -> Any:
        if self._agent is not None:
            return self._agent
        from flowjet.core.bridges.nano.adapter import create_nano_agent_instance

        self._agent = create_nano_agent_instance(self._config_path)
        return self._agent

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id=m) for m in self._models]

    async def delete_run(self, run_id: str) -> None:
        return None

    async def stream_run(self, request: RunRequest) -> AsyncIterator[RuntimeEvent]:
        agent = self._ensure_agent()
        run_id = request.run_id or f"resp_{uuid4().hex}"
        session = request.session or f"fj-{uuid4()}"
        workspace = None
        if request.metadata and isinstance(request.metadata.get("workspace"), str):
            workspace = request.metadata["workspace"]
        async for event in iter_nano_runtime_events(
            agent,
            run_id=run_id,
            model=request.model,
            session=session,
            input_text=request.input_text,
            workspace=workspace,
            thread_id=session,
            interaction_mode=InteractionMode.from_metadata(request.metadata),
            resume_value=request.resume_value,
        ):
            yield event


def build_isolating_nano_backend(
    *,
    models: list[str] | None = None,
    config_path: str | Path | None = None,
    home: Path | str | None = None,
    pool_settings: Any = None,
    allow_external_workspace: bool = False,
    workspace_resolver: Any = None,
    sandbox_manager: Any | None = None,
    checkpointer_policy: str | None = "off",
) -> Any:
    """Construct IsolatingRuntimeBackend with a NanoAgentAdapter factory."""
    return IsolatingBackendBuilder.build(
        NanoAgentAdapter,
        models=models,
        config_path=config_path,
        home=home,
        pool_settings=pool_settings,
        allow_external_workspace=allow_external_workspace,
        workspace_resolver=workspace_resolver,
        sandbox_manager=sandbox_manager,
        checkpointer_policy=checkpointer_policy,
    )


__all__ = ["NanoRuntimeBackend", "build_isolating_nano_backend"]
