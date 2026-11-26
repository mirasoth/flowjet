"""Per-session workspace resolution (RFC-002 / RFC-003, Phase 2 sync)."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from flowjet.core.runtime.isolation.errors import IsolationError

logger = logging.getLogger(__name__)

# A bare single-segment workspace id (e.g. a triarch workspace UUID). Used to
# key per-workspace sync runs; anything else (paths, empty, odd characters)
# falls back to the session-hash workspace. Mirrors soothe's run_id rules.
_WORKSPACE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def _run_id_for_session(session: str) -> str:
    """Session-scoped fallback run id (pre-Phase-2 behaviour)."""
    digest = hashlib.sha256(session.encode("utf-8")).hexdigest()[:16]
    return f"ws_{digest}"


def _workspace_id_from_metadata(metadata: dict[str, Any] | None) -> str | None:
    """Extract a bare workspace id from metadata["workspace"] (the ACP cwd).

    Only single-segment ids matching the run_id whitelist count as triarch
    workspace ids; path-shaped cwd values (flowjet-native desktop clients
    send absolute project paths) are NOT workspace ids — the caller falls
    back to a session-scoped workspace for them.
    """
    meta = metadata or {}
    override = meta.get("workspace")
    if not isinstance(override, str):
        return None
    candidate = override.strip()
    if "/" in candidate or "\\" in candidate or candidate in (".", ".."):
        return None
    if not _WORKSPACE_ID_RE.match(candidate):
        return None
    return candidate


class WorkspaceResolver:
    """Map session (+ optional metadata.workspace) to an absolute workspace path.

    The lifecycle hooks (``open_session`` / ``close_session``) are no-ops here
    — they exist so :class:`IsolatingRuntimeBackend` can call them uniformly
    whether the resolver is local-only or sync-backed (Phase 2).
    """

    def __init__(self, home: Path, *, allow_external_workspace: bool = False) -> None:
        self._home = Path(home).expanduser().resolve()
        self._allow_external = allow_external_workspace

    @property
    def home(self) -> Path:
        return self._home

    def resolve(self, session: str, metadata: dict[str, Any] | None = None) -> Path:
        meta = metadata or {}
        override = meta.get("workspace")
        if isinstance(override, str) and override.strip():
            path = Path(override.strip()).expanduser().resolve()
            if not self._allow_external and not self._is_under_home(path):
                raise IsolationError(
                    f"workspace override {path} is outside FLOWJET_HOME ({self._home}); "
                    "set FLOWJET_ALLOW_EXTERNAL_WORKSPACE=true to permit",
                    code="invalid_workspace",
                )
            path.mkdir(parents=True, exist_ok=True)
            return path

        digest = hashlib.sha256(session.encode("utf-8")).hexdigest()[:16]
        path = self._home / "data" / "workspaces" / f"ws_{digest}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def open_session(self, session: str, workspace: Path) -> None:
        """Hook called before a run starts. No-op for local-only workspaces."""

    async def close_session(self, session: str, workspace: Path) -> None:
        """Hook called after a run completes. No-op for local-only workspaces."""

    def _is_under_home(self, path: Path) -> bool:
        try:
            path.relative_to(self._home)
            return True
        except ValueError:
            return path == self._home


class SyncAwareWorkspaceResolver(WorkspaceResolver):
    """Workspace resolver backed by soothe's turn-scoped workspace sync.

    When ``workspace_sync_source`` is set, sessions materialize from /
    persist to an fsspec-backed object store (S3/GCS/Azure) via
    ``soothe.workspace.sync.TurnScopedWorkspaces``: the resolver maps the
    ACP cwd to a run id and delegates the per-turn lifecycle (manifest
    load, content-tree materialization, reconcile, dirty tracking,
    checkpoint commit — and ``TurnCommit`` persistence reporting) to the
    soothe facade. The resolver still returns a local
    :class:`~pathlib.Path` (the materialized workspace directory), so
    :class:`IsolatingRuntimeBackend` needs no change — only the lifecycle
    hooks differ.

    Single-root layout (IG-CORE-011): ``sync_source`` is the workspaces
    root URI (e.g. ``s3://bucket/workspaces``); each run's backend is
    rooted at ``<sync_source>/<run_id>`` and serves both the plain
    content tree (the authoritative file store) and the engine-private
    manifest.

    Lifecycle per session run::

        path = resolver.resolve(session, metadata)
        await resolver.open_session(session, path)  # materialize + start tracking
        # ... agent runs, writes to local filesystem ...
        commit = await resolver.close_session(session, path)  # checkpoint + close

    **Single-writer contract**: hosts must serialize turns per workspace —
    ``open_session``/``close_session`` must not interleave across sessions
    of the same workspace (agentspace enforces this at its prompt gate).

    When ``workspace_sync_source`` is **not** set at construction time, the
    resolver delegates to the base ``WorkspaceResolver`` (local-only, Phase 1
    behavior) and the lifecycle hooks are no-ops.
    """

    def __init__(
        self,
        home: Path,
        *,
        allow_external_workspace: bool = False,
        sync_source: str | None = None,
        sync_config: str | None = None,
        watched_subdirs: Sequence[str] | None = None,
    ) -> None:
        super().__init__(home, allow_external_workspace=allow_external_workspace)
        self._sync_source = sync_source
        self._sync_config = sync_config
        self._watched_subdirs = list(watched_subdirs) if watched_subdirs is not None else None
        self._engine: Any | None = None

    @property
    def is_sync_enabled(self) -> bool:
        """Return True when fsspec workspace sync is active."""
        return self._sync_source is not None and self._engine is not None

    def _ensure_engine(self) -> Any | None:
        """Lazily construct the turn-scoped sync engine (import + backend factory)."""
        if self._sync_source is None:
            return None
        if self._engine is not None:
            return self._engine

        from soothe.workspace.sync import TurnScopedWorkspaces

        backend_factory = self._backend_factory()
        workspaces_root = self._home / "data" / "workspaces"
        workspaces_root.mkdir(parents=True, exist_ok=True)
        self._engine = TurnScopedWorkspaces(
            workspaces_root=workspaces_root,
            backend_factory=backend_factory,
            watched_subdirs=self._watched_subdirs,
        )
        logger.info(
            "SyncAwareWorkspaceResolver initialized: source=%s, watched_subdirs=%s",
            self._sync_source,
            self._watched_subdirs,
        )
        return self._engine

    def _backend_factory(self) -> Any:
        """Build the per-run backend factory from the single sync source.

        Each run gets a backend rooted at ``<sync_source>/<run_id>``
        serving both the content tree and the manifest.  Cloud schemes
        (s3/gs/az) go through soothe's guarded ``construct_sync_backend``
        factory. ``file://`` URIs are built directly via fsspec
        (LocalFileSystem) — the factory's SSRF allowlist intentionally
        excludes local paths, but a local object store is a supported
        target for single-node deployments and tests.
        """
        base = (self._sync_source or "").rstrip("/")

        def factory(run_id: str) -> Any | None:
            uri = f"{base}/{run_id}"
            scheme = uri.split("://", 1)[0].lower()
            if scheme == "file":
                import fsspec
                from soothe.workspace.sync.backends.fsspec import FsspecSyncBackend

                fs, root = fsspec.url_to_fs(uri)
                return FsspecSyncBackend(fs=fs, root=str(root))
            from soothe.workspace.sync import construct_sync_backend

            return construct_sync_backend(uri, config=self._load_sync_config())

        return factory

    def _load_sync_config(self) -> dict[str, Any] | None:
        """Load optional sync config JSON (credentials, endpoint, etc.)."""
        if self._sync_config is None:
            return None
        import json

        path = Path(self._sync_config).expanduser()
        with path.open() as f:
            data: dict[str, Any] = json.load(f)
            return data

    def resolve(self, session: str, metadata: dict[str, Any] | None = None) -> Path:
        """Resolve workspace path — delegates to base when sync is disabled."""
        if self._sync_source is None:
            return super().resolve(session, metadata)
        # Phase 2: a bare workspace id in the ACP cwd (triarch backend sends
        # the workspaceId as cwd) keys a per-workspace sync run — all chats of
        # the same triarch workspace share one synced workspace. Anything
        # else falls back to the session-scoped hash (Phase 1 behaviour).
        run_id = _workspace_id_from_metadata(metadata) or _run_id_for_session(session)
        path = self._home / "data" / "workspaces" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def open_session(self, session: str, workspace: Path) -> None:
        """Refresh the workspace from the object store + start dirty tracking.

        RFC-RD-607 §4.3: the sync boundary is the agent turn (one pair of
        open/close hooks per prompt). The full inbound sequence — manifest
        load, content-tree materialization, reconcile, dirty tracking — is
        owned by the soothe turn-scoped facade
        (``TurnScopedWorkspaces.open_turn``).
        """
        engine = self._ensure_engine()
        if engine is None:
            return
        # The run_id is the workspace directory name — resolve() decided it
        # (triarch workspace id or session-hash fallback), so derive it here
        # for perfect consistency across resolve/open/close.
        await engine.open_turn(workspace.name)
        logger.info("Opened sync workspace for session %s at %s", session, workspace)

    async def close_session(self, session: str, workspace: Path) -> Any:
        """Checkpoint dirty files + upload to object store; close the turn.

        Returns the engine's :class:`~soothe.workspace.sync.TurnCommit`
        result (``persisted``/``version``/``error``) when sync is enabled,
        or ``None`` for local-only workspaces.  A failed commit keeps the
        workspace open (its dirty set survives to the next turn) and is
        reported via ``persisted=False`` — never raised.
        """
        if self._engine is None:
            return None
        return await self._engine.close_turn(workspace.name)

    async def shutdown(self) -> None:
        """Close all open workspaces on server shutdown."""
        if self._engine is None:
            return
        await self._engine.close_all()

    @classmethod
    def from_settings(
        cls,
        *,
        home: Path,
        sync_source: str,
        sync_config_path: str | None = None,
        allow_external_workspace: bool = False,
        watched_subdirs: Sequence[str] | None = None,
    ) -> SyncAwareWorkspaceResolver:
        """Build a resolver from server settings (called by ``build_backend``)."""
        return cls(
            home,
            allow_external_workspace=allow_external_workspace,
            sync_source=sync_source,
            sync_config=sync_config_path,
            watched_subdirs=watched_subdirs,
        )
