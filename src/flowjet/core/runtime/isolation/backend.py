"""RuntimeBackend that admits, resolves workspaces, and submits to the thread pool."""

from __future__ import annotations

import dataclasses
import logging
import traceback
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from flowjet.core.events import ModelInfo, RunCompleted, RunFailed, RunRequest, RuntimeEvent
from flowjet.core.ids import new_run_id, new_session_id
from flowjet.core.runtime.isolation.adapter import AdapterFactory
from flowjet.core.runtime.isolation.admission import SessionAdmission
from flowjet.core.runtime.isolation.mode_gate import InteractionModeGate
from flowjet.core.runtime.isolation.pool import PoolSettings, ThreadPool
from flowjet.core.runtime.isolation.request import IsolatedRunRequest
from flowjet.core.runtime.isolation.workspace import WorkspaceResolver

logger = logging.getLogger(__name__)


def _landed_input_text(
    session: str,
    workspace: Path,
    input_text: str,
    attachments: tuple[dict[str, str], ...],
) -> str:
    """Land wire image attachments and append their paths to the input text.

    The write goes into the materialized turn workspace (content-addressed,
    idempotent, shared helper from soothe). Attachments are engine-local
    cache under `.soothe/cache/attachments/` (soothe 1.3.9): never synced
    and invisible to the guest — the sandbox push/pull skip `.soothe/` —
    but the vision tools execute host-side and read the real paths, so the
    landed-paths note works in every sandbox mode. Stale attachments are
    pruned first (age-based TTL, local GC only). Landing failures degrade
    to the original text — the turn still runs text-only.
    """
    try:
        from soothe.workspace.attachments import (
            DEFAULT_ATTACHMENT_TTL_S,
            land_attachments,
            landed_paths_note,
            prune_attachments,
        )

        prune_attachments(workspace, max_age_s=DEFAULT_ATTACHMENT_TTL_S)
        paths = land_attachments(workspace, [dict(a) for a in attachments])
    except Exception:  # noqa: BLE001
        logger.warning(
            "Attachment landing failed (session=%s workspace=%s)",
            session,
            workspace,
            exc_info=True,
        )
        return input_text
    if not paths:
        return input_text
    note: str = landed_paths_note(paths)
    if input_text.strip():
        return f"{input_text}\n\n{note}"
    return note


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


def _persist_failure_event(error: str) -> RunFailed:
    """Build the terminal event for a failed workspace commit (IG-CORE-011).

    The turn produced its result but the workspace did not persist — turn
    completion = persisted, so the run outcome must reflect it.
    """
    return RunFailed(
        message=f"turn completed but workspace persistence failed: {error}",
        code="workspace_persist_failed",
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

    async def _close_workspace(self, session: str, workspace: Path) -> Any:
        """Close the workspace, converting failures into a persist-failed result.

        The sync resolver's ``close_session`` returns the engine's
        ``TurnCommit`` (duck-typed: ``persisted`` / ``error``); the
        local-only and sandbox resolvers return ``None`` (nothing to
        report).  Never raises — close failures surface through the
        result so the caller can decide the turn outcome.
        """
        try:
            return await self._workspaces.close_session(session, workspace)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "close_session failed for session %s (workspace=%s)",
                session,
                workspace,
                exc_info=True,
            )
            return SimpleNamespace(persisted=False, error=str(exc))

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
                    await self._close_workspace(session, workspace)
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "close_session after failed open failed (session=%s)",
                        session,
                        exc_info=True,
                    )
                yield _open_failure_event(exc)
                return
            # Land wire image attachments in the turn workspace (IG-CORE-012):
            # open_session has materialized the tree, so the engine-local
            # cache files exist before the agent runs. Failures degrade to a
            # text-only turn (never brick the run).
            if request.attachments:
                isolated = dataclasses.replace(
                    isolated,
                    input_text=_landed_input_text(
                        session, workspace, request.input_text, request.attachments
                    ),
                )
            closed = False
            try:
                # Hold the terminal event: the workspace commit runs BEFORE
                # the turn outcome is surfaced (turn completion = persisted,
                # IG-CORE-011).  Keep draining the pool generator to completion
                # so it consumes the worker's "done" control frame and releases
                # the worker (idle state / requests_completed) before we commit.
                # Breaking on the terminal event would abandon the generator
                # mid-stream, leaving the worker busy until async-generator
                # finalization and stalling subsequent requests.
                terminal: RuntimeEvent | None = None
                async for event in self._pool.submit(isolated):
                    if isinstance(event, RunCompleted | RunFailed):
                        terminal = event
                    else:
                        yield event
                commit = await self._close_workspace(session, workspace)
                closed = True
                if isinstance(terminal, RunCompleted) and not getattr(commit, "persisted", True):
                    yield _persist_failure_event(
                        str(getattr(commit, "error", None) or "unknown error")
                    )
                elif terminal is not None:
                    yield terminal
            finally:
                if not closed:
                    # Abort paths (consumer break mid-stream): best-effort
                    # close; the sync facade treats an already-closed run as
                    # a no-op commit.
                    await self._close_workspace(session, workspace)

    async def shutdown(self) -> None:
        await self._pool.shutdown()
        shutdown_ws = getattr(self._workspaces, "shutdown", None)
        if shutdown_ws is not None:
            result = shutdown_ws()
            if hasattr(result, "__await__"):
                await result
        self._started = False
