"""Tests for fj runtime config defaults."""

from __future__ import annotations

from pathlib import Path

import pytest
from soothe_nano.config import SootheConfig

from fj_ai.agent import apply_fj_defaults, ensure_workspace


def test_apply_fj_defaults_forces_sqlite() -> None:
    cfg = SootheConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": cfg.persistence.model_copy(update={"default_backend": "postgresql"}),
        }
    )
    assert cfg.resolve_checkpointer_backend() == "postgresql"
    forced = apply_fj_defaults(cfg)
    assert forced.resolve_checkpointer_backend() == "sqlite"


def test_apply_fj_defaults_sets_core_skills_when_unset() -> None:
    from fj_ai.agent import fj_core_skill_names

    cfg = SootheConfig()
    assert cfg.progressive_skills.core_skills is None
    forced = apply_fj_defaults(cfg)
    assert forced.progressive_skills.core_skills == fj_core_skill_names()
    # Nano defaults are included via DEFAULT_CORE_SKILL_NAMES, not hard-coded in fj.
    assert "weather" in forced.progressive_skills.core_skills
    assert "brainstorming" in forced.progressive_skills.core_skills


def test_apply_fj_defaults_preserves_explicit_core_skills() -> None:
    cfg = SootheConfig()
    cfg = cfg.model_copy(
        update={
            "progressive_skills": cfg.progressive_skills.model_copy(
                update={"core_skills": ["xlsx"]}
            ),
        }
    )
    forced = apply_fj_defaults(cfg)
    assert forced.progressive_skills.core_skills == ["xlsx"]


def test_apply_fj_defaults_disables_virtual_mode() -> None:
    cfg = SootheConfig()
    assert cfg.security.allow_paths_outside_workspace is False
    forced = apply_fj_defaults(cfg)
    assert forced.security.allow_paths_outside_workspace is True
    # Nano derives: virtual_mode = not allow_paths_outside_workspace
    virtual_mode = not forced.security.allow_paths_outside_workspace
    assert virtual_mode is False


def test_ensure_workspace_sets_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SOOTHE_WORKSPACE", raising=False)
    root = ensure_workspace(tmp_path)
    assert root == tmp_path.resolve()
    import os

    assert os.environ["SOOTHE_WORKSPACE"] == str(root)


@pytest.mark.asyncio
async def test_open_sqlite_checkpointer_yields_none_when_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fj_ai.agent as agent_mod

    monkeypatch.setattr(agent_mod, "resolve_checkpointer", lambda _cfg: None)
    async with agent_mod.open_sqlite_checkpointer(SootheConfig()) as cp:
        assert cp is None


@pytest.mark.asyncio
async def test_open_sqlite_checkpointer_opens_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import fj_ai.agent as agent_mod

    db_path = tmp_path / "checkpoints.db"
    monkeypatch.setattr(agent_mod, "resolve_checkpointer", lambda _cfg: (object(), str(db_path)))

    class FakeSaver:
        def __init__(self, conn: object, serde: object = None) -> None:
            self.conn = conn
            self.setup_called = False

        async def setup(self) -> None:
            self.setup_called = True

    class FakeConn:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    fake_conn = FakeConn()
    savers: list[FakeSaver] = []

    async def fake_connect(_path: str) -> FakeConn:
        return fake_conn

    def fake_saver(conn: object, serde: object = None) -> FakeSaver:
        saver = FakeSaver(conn, serde)
        savers.append(saver)
        return saver

    import aiosqlite
    import langgraph.checkpoint.sqlite.aio as aio_mod
    import soothe_sdk.utils.serde as serde_mod

    monkeypatch.setattr(aiosqlite, "connect", fake_connect)
    monkeypatch.setattr(aio_mod, "AsyncSqliteSaver", fake_saver)
    monkeypatch.setattr(serde_mod, "create_soothe_serde", lambda: object())

    async with agent_mod.open_sqlite_checkpointer(SootheConfig()) as cp:
        assert cp is savers[0]
        assert savers[0].setup_called is True
    assert fake_conn.closed is True


@pytest.mark.asyncio
async def test_build_agent_wires_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    import fj_ai.agent as agent_mod

    created: dict[str, object] = {}

    class FakeGraph:
        def __init__(self) -> None:
            self.checkpointer = None

    class FakeAgent:
        def __init__(self) -> None:
            self.graph = FakeGraph()

    def fake_create(_cfg: object) -> FakeAgent:
        agent = FakeAgent()
        created["agent"] = agent
        return agent

    monkeypatch.setattr(agent_mod, "configure_cli_logging", lambda **_k: None)
    monkeypatch.setattr(agent_mod, "ensure_workspace", lambda _w=None: Path.cwd())
    monkeypatch.setattr(agent_mod, "create_nano_agent", fake_create)
    monkeypatch.setattr(agent_mod, "silence_after_plugins", lambda **_k: None)

    cp = object()
    agent = await agent_mod.build_agent(SootheConfig(), checkpointer=cp, verbose=True)
    assert agent is created["agent"]
    assert agent.graph.checkpointer is cp
