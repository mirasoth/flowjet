"""Tests for fj runtime config defaults."""

from __future__ import annotations

from pathlib import Path

import pytest
from soothe_nano.config import SootheConfig

from fj_ai.agent import apply_ask_mode, apply_fj_defaults, ensure_workspace


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

    def fake_create(_cfg: object, **_kwargs: object) -> FakeAgent:
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


@pytest.mark.asyncio
async def test_build_agent_ask_mode_passes_interaction_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: ask mode must pass interaction_mode='ask' to create_nano_agent.

    apply_ask_mode() disables config tool groups, but write_file / edit_file come
    from soothe-nano's FilesystemMiddleware, whose tool surface is controlled by
    interaction_mode (FILESYSTEM_TOOLS_ASK vs FILESYSTEM_TOOLS_AGENT). Without
    interaction_mode='ask', the FS middleware keeps write_file / edit_file bound.
    """
    import fj_ai.agent as agent_mod

    captured: dict[str, object] = {}

    class FakeGraph:
        checkpointer = None

    class FakeAgent:
        def __init__(self) -> None:
            self.graph = FakeGraph()

    def fake_create(_cfg: object, **kwargs: object) -> FakeAgent:
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(agent_mod, "configure_cli_logging", lambda **_k: None)
    monkeypatch.setattr(agent_mod, "ensure_workspace", lambda _w=None: Path.cwd())
    monkeypatch.setattr(agent_mod, "create_nano_agent", fake_create)
    monkeypatch.setattr(agent_mod, "silence_after_plugins", lambda **_k: None)

    await agent_mod.build_agent(SootheConfig(), ask_mode=True)
    assert captured.get("interaction_mode") == "ask"


@pytest.mark.asyncio
async def test_build_agent_default_mode_no_interaction_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-ask mode must not pass interaction_mode='ask'."""
    import fj_ai.agent as agent_mod

    captured: dict[str, object] = {}

    class FakeGraph:
        checkpointer = None

    class FakeAgent:
        def __init__(self) -> None:
            self.graph = FakeGraph()

    def fake_create(_cfg: object, **kwargs: object) -> FakeAgent:
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(agent_mod, "configure_cli_logging", lambda **_k: None)
    monkeypatch.setattr(agent_mod, "ensure_workspace", lambda _w=None: Path.cwd())
    monkeypatch.setattr(agent_mod, "create_nano_agent", fake_create)
    monkeypatch.setattr(agent_mod, "silence_after_plugins", lambda **_k: None)

    await agent_mod.build_agent(SootheConfig(), ask_mode=False)
    assert captured.get("interaction_mode") != "ask"


# ---------------------------------------------------------------------------
# Ask mode
# ---------------------------------------------------------------------------


def test_apply_ask_mode_disables_all_tool_groups() -> None:
    cfg = apply_fj_defaults(SootheConfig())
    forced = apply_ask_mode(cfg)
    assert forced.tools.execution.enabled is False
    assert forced.tools.file_ops.enabled is False
    assert forced.tools.datetime.enabled is False
    assert forced.tools.data.enabled is False
    assert forced.tools.wizsearch.enabled is False
    assert forced.tools.http_requests.enabled is False
    assert forced.tools.deepxiv.enabled is False


def test_apply_ask_mode_disables_progressive_discovery() -> None:
    cfg = apply_fj_defaults(SootheConfig())
    forced = apply_ask_mode(cfg)
    assert forced.progressive_tools.enabled is False
    assert forced.progressive_tools.search_tools_enabled is False
    assert forced.progressive_skills.search_skills_enabled is False
    assert forced.progressive_skills.semantic_search_enabled is False


def test_apply_ask_mode_sets_readonly_policy_profile() -> None:
    cfg = apply_fj_defaults(SootheConfig())
    assert cfg.agent.protocols.policy.profile == "standard"
    forced = apply_ask_mode(cfg)
    assert forced.agent.protocols.policy.profile == "readonly"


def test_apply_ask_mode_appends_prompt_suffix() -> None:
    cfg = apply_fj_defaults(SootheConfig())
    original = cfg.agent.system_prompt or ""
    forced = apply_ask_mode(cfg)
    new_prompt = forced.agent.system_prompt or ""
    assert "ASK MODE" in new_prompt
    if original:
        assert new_prompt.startswith(original)
        assert len(new_prompt) > len(original)


def test_apply_ask_mode_preserves_sqlite_persistence() -> None:
    """Ask mode layers on top of fj defaults; sqlite must stay forced."""
    cfg = SootheConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": cfg.persistence.model_copy(update={"default_backend": "postgresql"}),
        }
    )
    forced = apply_ask_mode(apply_fj_defaults(cfg))
    assert forced.resolve_checkpointer_backend() == "sqlite"


@pytest.mark.asyncio
async def test_build_agent_ask_mode_uses_ask_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_agent(ask_mode=True) must pass ask-mode config + interaction_mode.

    apply_ask_mode() disables config tool groups; interaction_mode='ask'
    switches soothe-nano's FilesystemMiddleware to FILESYSTEM_TOOLS_ASK so
    write_file / edit_file are not bound.
    """
    import fj_ai.agent as agent_mod

    received: dict[str, object] = {}

    class FakeGraph:
        def __init__(self) -> None:
            self.checkpointer = None

    class FakeAgent:
        def __init__(self) -> None:
            self.graph = FakeGraph()

    def fake_create(cfg: object, **kwargs: object) -> FakeAgent:
        received["cfg"] = cfg
        received["kwargs"] = kwargs
        return FakeAgent()

    monkeypatch.setattr(agent_mod, "configure_cli_logging", lambda **_k: None)
    monkeypatch.setattr(agent_mod, "ensure_workspace", lambda _w=None: Path.cwd())
    monkeypatch.setattr(agent_mod, "create_nano_agent", fake_create)
    monkeypatch.setattr(agent_mod, "silence_after_plugins", lambda **_k: None)

    await agent_mod.build_agent(SootheConfig(), ask_mode=True)

    cfg = received["cfg"]
    # The config handed to create_nano_agent must have tools disabled.
    assert cfg.tools.execution.enabled is False
    assert cfg.tools.file_ops.enabled is False
    assert cfg.agent.protocols.policy.profile == "readonly"
    # Regression: interaction_mode='ask' must be forwarded so the FS middleware
    # binds the read-only surface (no write_file / edit_file).
    assert received["kwargs"].get("interaction_mode") == "ask"
