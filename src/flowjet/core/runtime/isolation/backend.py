"""RuntimeBackend that admits, resolves workspaces, and submits to the thread pool."""

from __future__ import annotations

import logging
import traceback
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from flowjet.core.events import ModelInfo, RunFailed, RunRequest, RuntimeEvent
from flowjet.core.ids import new_run_id, new_session_id
from flowjet.core.runtime.isolation.adapter import AdapterFactory
from flowjet.core.runtime.isolation.admission import SessionAdmission
from flowjet.core.runtime.isolation.mode_gate import InteractionModeGate
from flowjet.core.runtime.isolation.pool import PoolSettings, ThreadPool
from flowjet.core.runtime.isolation.request import IsolatedRunRequest
from flowjet.core.runtime.isolation.workspace import WorkspaceResolver

logger = logging.getLogger(__name__)


def _open_failure_event(exc: BaseException) -> RunFailed:
    """Mirror the pool's worker-error conversion for workspace-open failures."""
    tb_text: str | None = None
    if exc.__traceback__ is not None:
        tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return RunFailed(
        message=str(exc) or type(exc).__name__,
        code="workspace_open_error",
        exc_type=type(exc).__name__,
        traceback=tb_text,
    )


class IsolatingRuntimeBackend:
    """Pool-backed RuntimeBackend for the soothe/nano AgentAdapter.

    Concurrency layering (two gates, each load-bearing at its layer):

    * :class:`SessionAdmission` serializes the whole session *lifecycle*
      (workspace open → run → close) in :meth:`stream_run` — concurrent turns
      of one session never interleave workspace materialization or
      checkpointing.
    * :class:`ThreadPool` independently serializes same-session submits for
      direct pool users; under this backend the pool gate never fires because
      admission already holds.

    The workspace resolver is injectable: callers can pass a
    :class:`SyncAwareWorkspaceResolver` to enable fsspec workspace sync.
    The default is the local-only :class:`WorkspaceResolver`.
    """

    def __init__(
        self,
        *,
        models: list[str] | None = None,
        adapter_factory: AdapterFactory,
        pool_settings: PoolSettings | None = None,
        home: Path | str | None = None,
        admission: SessionAdmission | None = None,
        mode_gate: InteractionModeGate | None = None,
        workspace_resolver: WorkspaceResolver | None = None,
        allow_external_workspace: bool = False,
    ) -> None:
        self._models = models or ["default"]
        home_path = Path(home).expanduser() if home else Path.home() / ".flowjet"
        self._workspaces = workspace_resolver or WorkspaceResolver(
            home_path, allow_external_workspace=allow_external_workspace
        )
        self._admission = admission or SessionAdmission()
        self._mode_gate = mode_gate or InteractionModeGate()
        self._pool = ThreadPool(adapter_factory, pool_settings)
        self._started = False

    @property
    def pool(self) -> ThreadPool:
        return self._pool

    @property
    def workspaces(self) -> WorkspaceResolver:
        return self._workspaces

    def pool_metrics(self) -> dict[str, Any]:
        m = self._pool.metrics()
        return {
            "total_workers": m.total_workers,
            "idle_workers": m.idle_workers,
            "busy_workers": m.busy_workers,
            "dead_workers": m.dead_workers,
            "requests_completed": m.requests_completed,
            "ready_timeouts": m.ready_timeouts,
            "events_dropped": m.events_dropped,
        }

    async def _ensure_started(self) -> None:
        if not self._started:
            await self._pool.start()
            self._started = True

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id=m) for m in self._models]

    async def delete_run(self, run_id: str) -> None:
        self._pool.cancel_run(run_id)

    async def stream_run(self, request: RunRequest) -> AsyncIterator[RuntimeEvent]:
        await self._ensure_started()
        session = request.session or new_session_id()
        run_id = request.run_id or new_run_id()
        metadata = dict(request.metadata or {})
        mode = await self._mode_gate.resolve(session, metadata)
        metadata["interaction_mode"] = mode
        workspace = self._workspaces.resolve(session, metadata)
        isolated = IsolatedRunRequest(
            run_id=run_id,
            session=session,
            input_text=request.input_text,
            model=request.model,
            workspace=workspace,
            thread_id=session,
            metadata=metadata,
            resume_value=request.resume_value,
        )
        async with self._admission.admit(session):
            try:
                await self._workspaces.open_session(session, workspace)
            except Exception as exc:  # noqa: BLE001
                # A failed workspace open (e.g. the sandbox disk watermark) never
                # reaches the pool worker, so its RunFailed conversion never
                # happens: the raw exception would escape as a protocol error
                # with no terminal event. Surface it as one — after a
                # best-effort close to keep the resolver's open/close pairing
                # balanced (sandbox leases roll back their own run count).
                logger.warning(
                    "Workspace open failed for session %s (workspace=%s)",
                    session,
                    workspace,
                    exc_info=True,
                )
                try:
                    await self._workspaces.close_session(session, workspace)
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "close_session after failed open failed (session=%s)",
                        session,
                        exc_info=True,
                    )
                yield _open_failure_event(exc)
                return
            try:
                async for event in self._pool.submit(isolated):
                    yield event
            finally:
                await self._workspaces.close_session(session, workspace)

    async def shutdown(self) -> None:
        await self._pool.shutdown()
        shutdown_ws = getattr(self._workspaces, "shutdown", None)
        if shutdown_ws is not None:
            result = shutdown_ws()
            if hasattr(result, "__await__"):
                await result
        self._started = False
