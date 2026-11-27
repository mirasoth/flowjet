"""Phase 2 — workspace sync (fsspec) integration tests.

Tests the ``SyncAwareWorkspaceResolver`` lifecycle hooks and the
``IsolatingRuntimeBackend`` integration with an injectable resolver. The
per-turn engine semantics (shared open, reconcile gating, artifact restore,
last-turn-out close) live in soothe's ``TurnScopedWorkspaces`` and are
pinned by that repo's ``test_turns.py``; here we pin the resolver's
session→run_id mapping, its delegation to the engine, and — with real
``file://`` backends — the end-to-end dual-source round trip.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from flowjet.core.events import RunCompleted, RunFailed, RunRequest, RunStarted
from flowjet.core.runtime.isolation import (
    FakeAgentAdapter,
    IsolatedRunRequest,
    IsolatingRuntimeBackend,
    PoolSettings,
    SyncAwareWorkspaceResolver,
    WorkspaceResolver,
)


class FakeEngine:
    """Duck-typed ``TurnScopedWorkspaces`` recording the delegated run ids."""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.closed: list[str] = []
        self.close_all_calls = 0

    async def open_turn(self, run_id: str) -> Path:
        self.opened.append(run_id)
        return Path("/unused")

    async def close_turn(self, run_id: str) -> None:
        self.closed.append(run_id)

    async def close_all(self) -> None:
        self.close_all_calls += 1


# ---------------------------------------------------------------------------
# WorkspaceResolver lifecycle hooks (base class — Phase 1 no-ops)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_resolver_open_close_are_noops(tmp_path: Path):
    """Base WorkspaceResolver lifecycle hooks are no-ops (no sync)."""
    resolver = WorkspaceResolver(tmp_path)
    path = resolver.resolve("session-x")
    # These should not raise and should return None.
    await resolver.open_session("session-x", path)
    await resolver.close_session("session-x", path)


# ---------------------------------------------------------------------------
# Phase 2 — per-workspace run_id keyed by ACP cwd (triarch workspaceId)
# ---------------------------------------------------------------------------


def test_resolve_uses_workspace_id_from_cwd(tmp_path: Path):
    """A bare workspace id in the ACP cwd keys the workspace path/run_id."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    path = resolver.resolve("session-1", {"workspace": "0f1e2d3c-4b5a-6978-87a6-b5c4d3e2f1a0"})
    assert path.name == "0f1e2d3c-4b5a-6978-87a6-b5c4d3e2f1a0"
    assert path.parent == tmp_path / "data" / "workspaces"


def test_resolve_same_workspace_id_across_sessions_shares_path(tmp_path: Path):
    """Different sessions with the same cwd wsId resolve to one workspace."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    ws_id = "ws-alpha-123"
    p1 = resolver.resolve("session-1", {"workspace": ws_id})
    p2 = resolver.resolve("session-2", {"workspace": ws_id})
    assert p1 == p2


def test_resolve_falls_back_to_session_hash_for_path_cwd(tmp_path: Path):
    """Path-shaped cwd (desktop client project dir) is NOT a workspace id."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    path = resolver.resolve("session-1", {"workspace": "/Users/x/project"})
    assert path.name.startswith("ws_")
    assert len(path.name) == len("ws_") + 16


@pytest.mark.parametrize(
    "bad",
    ["", "  ", "..", ".", "has/slash", "a b", "-leading-dash", "x" * 129],
)
def test_resolve_falls_back_for_invalid_workspace_ids(tmp_path: Path, bad: str):
    """Ids failing the whitelist fall back to the session-hash workspace."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    path = resolver.resolve("session-1", {"workspace": bad})
    assert path.name.startswith("ws_")


# ---------------------------------------------------------------------------
# Lifecycle delegation to the turn-scoped engine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_close_delegate_run_id_to_engine(tmp_path: Path):
    """open/close derive the run_id from the resolved path name (wsId)."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    engine = FakeEngine()
    resolver._engine = engine

    ws_id = "0f1e2d3c-4b5a-6978-87a6-b5c4d3e2f1a0"
    path = resolver.resolve("session-1", {"workspace": ws_id})
    await resolver.open_session("session-1", path)
    await resolver.close_session("session-1", path)
    assert engine.opened == [ws_id]
    assert engine.closed == [ws_id]


@pytest.mark.asyncio
async def test_two_sessions_same_workspace_delegate_same_run_id(tmp_path: Path):
    """Both sessions hand the same run_id to the engine.

    Concurrent-turn sharing (one open workspace, last-turn-out close) is the
    engine's contract — pinned in soothe's test_turns.py.
    """
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    engine = FakeEngine()
    resolver._engine = engine

    ws_id = "shared-ws"
    p1 = resolver.resolve("session-a", {"workspace": ws_id})
    p2 = resolver.resolve("session-b", {"workspace": ws_id})
    await resolver.open_session("session-a", p1)
    await resolver.open_session("session-b", p2)
    await resolver.close_session("session-a", p1)
    await resolver.close_session("session-b", p2)
    assert engine.opened == [ws_id, ws_id]
    assert engine.closed == [ws_id, ws_id]


@pytest.mark.asyncio
async def test_close_session_without_engine_is_safe(tmp_path: Path):
    """close_session before any open (engine never built) should not raise."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    path = resolver.resolve("session-noopen")
    await resolver.close_session("session-noopen", path)


@pytest.mark.asyncio
async def test_shutdown_delegates_to_engine(tmp_path: Path):
    """shutdown calls engine.close_all."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    engine = FakeEngine()
    resolver._engine = engine
    await resolver.shutdown()
    assert engine.close_all_calls == 1


@pytest.mark.asyncio
async def test_shutdown_without_engine_is_noop(tmp_path: Path):
    """shutdown before the engine is built should not raise."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    await resolver.shutdown()


def test_is_sync_enabled_false_until_engine_is_built(tmp_path: Path):
    """A configured sync source only counts as enabled once the engine exists."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source="s3://b/p")
    assert resolver.is_sync_enabled is False


# ---------------------------------------------------------------------------
# SyncAwareWorkspaceResolver — disabled mode (no sync_source)
# ---------------------------------------------------------------------------


def test_sync_resolver_without_source_delegates_to_base(tmp_path: Path):
    """Without sync_source, SyncAwareWorkspaceResolver behaves like base."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source=None)
    assert resolver.is_sync_enabled is False

    path = resolver.resolve("session-a")
    assert path.is_dir()
    assert path.parent == tmp_path / "data" / "workspaces"


@pytest.mark.asyncio
async def test_sync_resolver_without_source_hooks_are_noops(tmp_path: Path):
    """Without sync_source, lifecycle hooks are no-ops."""
    resolver = SyncAwareWorkspaceResolver(tmp_path, sync_source=None)
    path = resolver.resolve("session-a")
    await resolver.open_session("session-a", path)
    await resolver.close_session("session-a", path)
    assert resolver.is_sync_enabled is False


# ---------------------------------------------------------------------------
# SyncAwareWorkspaceResolver.from_settings
# ---------------------------------------------------------------------------


def test_from_settings_constructs_resolver(tmp_path: Path):
    """from_settings builds a resolver with all fields wired."""
    resolver = SyncAwareWorkspaceResolver.from_settings(
        home=tmp_path,
        sync_source="s3://bucket/flowjet",
        sync_config_path=None,
        allow_external_workspace=True,
    )
    assert isinstance(resolver, SyncAwareWorkspaceResolver)
    assert resolver._sync_source == "s3://bucket/flowjet"
    assert resolver._allow_external is True


# ---------------------------------------------------------------------------
# IsolatingRuntimeBackend — injectable resolver + lifecycle hooks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backend_calls_lifecycle_hooks(tmp_path: Path):
    """IsolatingRuntimeBackend calls open_session/close_session around each run."""
    open_calls: list[str] = []
    close_calls: list[str] = []

    class TrackingResolver(WorkspaceResolver):
        async def open_session(self, session: str, workspace: Path) -> None:
            open_calls.append(session)

        async def close_session(self, session: str, workspace: Path) -> None:
            close_calls.append(session)

    backend = IsolatingRuntimeBackend(
        adapter_factory=FakeAgentAdapter,
        pool_settings=PoolSettings(min_size=1, max_size=1),
        home=tmp_path,
        workspace_resolver=TrackingResolver(tmp_path),
    )
    try:
        events = [
            e
            async for e in backend.stream_run(
                RunRequest(
                    input_text="hello",
                    model="default",
                    session="fj-lifecycle",
                )
            )
        ]
        assert any(isinstance(e, RunStarted) for e in events)
        assert any(isinstance(e, RunCompleted) for e in events)
        assert open_calls == ["fj-lifecycle"]
        assert close_calls == ["fj-lifecycle"]
    finally:
        await backend.shutdown()


@pytest.mark.asyncio
async def test_backend_close_session_called_on_failure(tmp_path: Path):
    """close_session is called even when the run raises."""
    open_calls: list[str] = []
    close_calls: list[str] = []

    class TrackingResolver(WorkspaceResolver):
        async def open_session(self, session: str, workspace: Path) -> None:
            open_calls.append(session)

        async def close_session(self, session: str, workspace: Path) -> None:
            close_calls.append(session)

    class CrashAdapter:
        async def astream(self, req: IsolatedRunRequest):
            yield RunStarted(run_id=req.run_id, model=req.model, session=req.session)
            raise RuntimeError("agent crashed")

        def prepare_for_request(self) -> None:
            pass

        async def cleanup(self) -> None:
            pass

    backend = IsolatingRuntimeBackend(
        adapter_factory=CrashAdapter,
        pool_settings=PoolSettings(min_size=1, max_size=1),
        home=tmp_path,
        workspace_resolver=TrackingResolver(tmp_path),
    )
    try:
        [
            e
            async for e in backend.stream_run(
                RunRequest(
                    input_text="boom",
                    model="default",
                    session="fj-crash",
                )
            )
        ]
        # open should have been called.
        assert open_calls == ["fj-crash"]
        # close should have been called even after the crash.
        assert close_calls == ["fj-crash"]
    finally:
        await backend.shutdown()


@pytest.mark.asyncio
async def test_backend_shutdown_calls_resolver_shutdown(tmp_path: Path):
    """Backend.shutdown calls resolver.shutdown if it exists."""
    shutdown_calls: list[bool] = []

    class ShutdownResolver(WorkspaceResolver):
        async def shutdown(self) -> None:
            shutdown_calls.append(True)

    backend = IsolatingRuntimeBackend(
        adapter_factory=FakeAgentAdapter,
        pool_settings=PoolSettings(min_size=1, max_size=1),
        home=tmp_path,
        workspace_resolver=ShutdownResolver(tmp_path),
    )
    await backend.shutdown()
    assert shutdown_calls == [True]


# ---------------------------------------------------------------------------
# Phase 3 — single-root sync (content materialization + mirror write-back)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_session_materializes_content_root(tmp_path: Path):
    """open_session pulls the run's content tree into the workspace.

    Full chain with file:// backends: host materials land in the workspace
    directory the agent will run in, keyed by the ACP cwd wsId.
    """
    # The host uploads a material into the workspace's content tree.
    content_root = tmp_path / "remote" / "ws-alpha"
    (content_root / "materials" / "m1").mkdir(parents=True)
    (content_root / "materials" / "m1" / "notes.md").write_bytes(b"material v1")

    resolver = SyncAwareWorkspaceResolver(
        tmp_path,
        sync_source=f"file://{tmp_path}/remote",
    )

    ws_id = "ws-alpha"
    path = resolver.resolve("session-1", {"workspace": ws_id})
    await resolver.open_session("session-1", path)

    # The material is visible at the agent-visible workspace path.
    assert (path / "materials" / "m1" / "notes.md").read_bytes() == b"material v1"
    await resolver.shutdown()


@pytest.mark.asyncio
async def test_checkpoint_mirrors_agent_outputs_to_content_root(tmp_path: Path):
    """close_session checkpoints dirty files back into the content tree."""
    remote = tmp_path / "remote"

    resolver = SyncAwareWorkspaceResolver(
        tmp_path,
        sync_source=f"file://{remote}",
    )

    ws_id = "ws-beta"
    path = resolver.resolve("session-1", {"workspace": ws_id})
    await resolver.open_session("session-1", path)

    # The agent writes an output file into the workspace.
    out = path / "output" / "analysis.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"agent analysis")

    # close_session → checkpoint → dirty files mirrored to the content
    # tree; the manifest commits under the engine key space.
    commit = await resolver.close_session("session-1", path)
    assert getattr(commit, "persisted") is True
    assert (remote / ws_id / "output" / "analysis.md").read_bytes() == b"agent analysis"
    # Manifest key: `.soothe/manifest.json` since IG-CORE-013 (the legacy
    # `.workspace/` key is retired — do not pin it back).
    assert (remote / ws_id / ".soothe" / "manifest.json").exists()
    await resolver.shutdown()


@pytest.mark.asyncio
async def test_close_session_reports_failed_commit(tmp_path: Path, monkeypatch):
    """A failing commit surfaces via the TurnCommit result, never raises."""
    from soothe.workspace.sync.backends.fsspec import FsspecSyncBackend

    async def _fail_upload(self, rel_path: str, src: Path) -> None:
        raise OSError("injected upload failure")

    monkeypatch.setattr(FsspecSyncBackend, "put_content_file_from_file", _fail_upload)

    remote = tmp_path / "remote"
    remote.mkdir()

    resolver = SyncAwareWorkspaceResolver(
        tmp_path,
        sync_source=f"file://{remote}",
    )

    path = resolver.resolve("session-1", {"workspace": "ws-gamma"})
    await resolver.open_session("session-1", path)

    (path / "output" / "a.md").parent.mkdir(parents=True, exist_ok=True)
    (path / "output" / "a.md").write_bytes(b"a")

    commit = await resolver.close_session("session-1", path)
    assert getattr(commit, "persisted") is False
    assert "partially" in (getattr(commit, "error", "") or "")
    assert "output/a.md" in (getattr(commit, "error", "") or "")
    await resolver.shutdown()


@pytest.mark.asyncio
async def test_backend_fails_the_turn_when_persistence_fails(tmp_path: Path):
    """IG-CORE-011: a successful run whose workspace commit failed ends as
    RunFailed(code=workspace_persist_failed) — turn completion = persisted."""

    class PersistFailResolver(WorkspaceResolver):
        async def close_session(self, session: str, workspace: Path):
            return SimpleNamespace(persisted=False, error="upload exploded")

    backend = IsolatingRuntimeBackend(
        adapter_factory=FakeAgentAdapter,
        pool_settings=PoolSettings(min_size=1, max_size=1),
        home=tmp_path,
        workspace_resolver=PersistFailResolver(tmp_path),
    )
    try:
        events = [
            e
            async for e in backend.stream_run(
                RunRequest(input_text="hello", model="default", session="fj-persist")
            )
        ]
        terminals = [e for e in events if isinstance(e, (RunCompleted, RunFailed))]
        assert len(terminals) == 1
        terminal = terminals[0]
        assert isinstance(terminal, RunFailed)
        assert terminal.code == "workspace_persist_failed"
        assert "upload exploded" in (terminal.message or "")
    finally:
        await backend.shutdown()


@pytest.mark.asyncio
async def test_backend_run_completed_surfaces_on_clean_commit(tmp_path: Path):
    """A clean commit (or a non-sync resolver) still ends as RunCompleted."""

    class CleanCommitResolver(WorkspaceResolver):
        async def close_session(self, session: str, workspace: Path):
            return SimpleNamespace(persisted=True, version=1, error=None)

    backend = IsolatingRuntimeBackend(
        adapter_factory=FakeAgentAdapter,
        pool_settings=PoolSettings(min_size=1, max_size=1),
        home=tmp_path,
        workspace_resolver=CleanCommitResolver(tmp_path),
    )
    try:
        events = [
            e
            async for e in backend.stream_run(
                RunRequest(input_text="hello", model="default", session="fj-clean")
            )
        ]
        terminals = [e for e in events if isinstance(e, (RunCompleted, RunFailed))]
        assert len(terminals) == 1
        assert isinstance(terminals[0], RunCompleted)
    finally:
        await backend.shutdown()


# ---------------------------------------------------------------------------
# Server config — workspace sync settings
# ---------------------------------------------------------------------------


def test_settings_workspace_sync_defaults():
    """Settings defaults for workspace sync are Phase 1 (disabled)."""
    from flowjet.server.config import Settings

    s = Settings()
    assert s.workspace_sync_source is None
    assert s.workspace_sync_config is None
    assert not hasattr(s, "workspace_content_source")


def test_settings_workspace_sync_from_env(monkeypatch):
    """Settings can be configured via env vars."""
    from flowjet.server.config import Settings

    monkeypatch.setenv("FLOWJET_WORKSPACE_SYNC_SOURCE", "s3://bucket/workspaces")
    s = Settings()
    assert s.workspace_sync_source == "s3://bucket/workspaces"


# ---------------------------------------------------------------------------
# build_backend — workspace resolver wiring
# ---------------------------------------------------------------------------


def test_build_backend_returns_none_resolver_when_no_sync(tmp_path: Path):
    """build_backend without sync_source passes workspace_resolver=None."""
    from flowjet.server.config import Settings
    from flowjet.server.http.app import build_workspace_resolver

    s = Settings(home=str(tmp_path))
    resolver = build_workspace_resolver(s)
    assert resolver is None


def test_build_backend_builds_sync_resolver_when_configured(tmp_path: Path, monkeypatch):
    """build_backend with sync_source constructs a SyncAwareWorkspaceResolver."""
    from flowjet.server.config import Settings
    from flowjet.server.http.app import build_workspace_resolver

    monkeypatch.setenv("FLOWJET_HOME", str(tmp_path))
    monkeypatch.setenv("FLOWJET_WORKSPACE_SYNC_SOURCE", "s3://bucket/workspaces")
    s = Settings()
    resolver = build_workspace_resolver(s)
    assert resolver is not None
    assert isinstance(resolver, SyncAwareWorkspaceResolver)
    assert resolver._sync_source == "s3://bucket/workspaces"
