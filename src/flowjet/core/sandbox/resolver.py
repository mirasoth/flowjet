"""Workspace-resolver decorator that stages the workspace through the sandbox."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flowjet.core.sandbox.arbox import ArcBoxToolSandboxManager


class SandboxAwareWorkspaceResolver:
    """Resolver decorator that stages the workspace through the sandbox.

    Wraps the existing resolver (local-only or sync-backed): the inner
    resolver's lifecycle runs first on open (S3 materialization) and last on
    close (S3 checkpoint), with the host↔guest transfer sandwiched between —
    the guest pull must land before the sync checkpoint sees the workspace.
    """

    def __init__(self, inner: Any, manager: ArcBoxToolSandboxManager) -> None:
        self._inner = inner
        self._manager = manager

    @property
    def manager(self) -> ArcBoxToolSandboxManager:
        return self._manager

    def resolve(self, session: str, metadata: dict[str, Any] | None = None) -> Path:
        return Path(self._inner.resolve(session, metadata))

    async def open_session(self, session: str, workspace: Path) -> None:
        await self._inner.open_session(session, workspace)
        await self._manager.open_workspace(str(workspace))

    async def close_session(self, session: str, workspace: Path) -> None:
        await self._manager.close_workspace(str(workspace))
        await self._inner.close_session(session, workspace)

    async def shutdown(self) -> None:
        await self._manager.shutdown()
        shutdown_inner = getattr(self._inner, "shutdown", None)
        if shutdown_inner is not None:
            result = shutdown_inner()
            if hasattr(result, "__await__"):
                await result

    def __getattr__(self, name: str) -> Any:
        # Transparent delegation for anything else (e.g. is_sync_enabled).
        return getattr(self._inner, name)


__all__ = ["SandboxAwareWorkspaceResolver"]
