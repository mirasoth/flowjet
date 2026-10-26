"""Tests for fj runtime config defaults."""

from __future__ import annotations

from pathlib import Path

import pytest
from soothe_nano.config import SootheConfig

from flowjet.cli.agent import apply_fj_defaults, ensure_workspace


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
    from flowjet.cli.agent import fj_core_skill_names

    cfg = SootheConfig()
    assert cfg.progressive_skills.core_skills is None
    forced = apply_fj_defaults(cfg)
    assert forced.progressive_skills.core_skills == fj_core_skill_names()
    # Nano defaults are included via DEFAULT_CORE_SKILL_NAMES, not hard-coded in fj.
    assert "weather" in forced.progressive_skills.core_skills


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
    import flowjet.core.agent.workspace as workspace_mod
    from flowjet.core.agent.workspace import Checkpointers

    monkeypatch.setattr(workspace_mod, "resolve_checkpointer", lambda _cfg: None)
    async with Checkpointers.open_sqlite(SootheConfig()) as cp:
        assert cp is None


@pytest.mark.asyncio
async def test_open_honors_config_backend_sqlite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Checkpointers.open resolves the backend from the config (server path)."""
    import flowjet.core.agent.workspace as workspace_mod
    from flowjet.core.agent.workspace import Checkpointers

    db_path = tmp_path / "checkpoints.db"
    monkeypatch.setattr(workspace_mod, "resolve_checkpointer", lambda _cfg: (None, str(db_path)))
    # Default config: durability.checkpointer="default" inherits
    # persistence.default_backend="sqlite".
    async with Checkpointers.open(SootheConfig()) as cp:
        assert cp is not None
    assert db_path.parent.exists()


@pytest.mark.asyncio
async def test_open_uses_shared_pool_for_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL is wired server-side: an AsyncPostgresSaver on the shared pool."""
    import flowjet.core.agent.workspace as workspace_mod
    from flowjet.core.agent.workspace import Checkpointers

    class FakePool:
        def __init__(self) -> None:
            self.opened = False

        async def open(self) -> None:
            self.opened = True

    pool = FakePool()
    monkeypatch.setattr(workspace_mod, "resolve_checkpointer", lambda _cfg: (None, pool))
    setups: list[object] = []

    async def fake_setup(cfg: object, saver: object) -> object:
        setups.append(saver)
        return saver

    monkeypatch.setattr(workspace_mod, "_setup_postgres", fake_setup)

    cfg = SootheConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": cfg.persistence.model_copy(update={"default_backend": "postgresql"}),
        }
    )
    async with Checkpointers.open(cfg) as cp:
        assert cp is not None
        assert type(cp).__name__ == "AsyncPostgresSaver"
    assert pool.opened is True
    assert len(setups) == 1


@pytest.mark.asyncio
async def test_open_degrades_to_none_when_postgres_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A PostgreSQL failure degrades to "no persistence" — it must not crash."""
    import flowjet.core.agent.workspace as workspace_mod
    from flowjet.core.agent.workspace import Checkpointers

    def boom(_cfg: object) -> object:
        raise RuntimeError("pool unavailable")

    monkeypatch.setattr(workspace_mod, "resolve_checkpointer", boom)
    cfg = SootheConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": cfg.persistence.model_copy(update={"default_backend": "postgresql"}),
        }
    )
    async with Checkpointers.open(cfg) as cp:
        assert cp is None


@pytest.mark.asyncio
async def test_open_warns_and_yields_none_for_unwired_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown backend degrades, doesn't crash."""
    from flowjet.core.agent.workspace import Checkpointers

    cfg = SootheConfig()
    monkeypatch.setattr(
        type(cfg), "resolve_checkpointer_backend", lambda _self: "mysql", raising=False
    )
    async with Checkpointers.open(cfg) as cp:
        assert cp is None


def test_checkpointer_policy_enabled() -> None:
    from flowjet.core.agent.workspace import checkpointer_policy_enabled

    assert checkpointer_policy_enabled("auto") is True
    assert checkpointer_policy_enabled("AUTO") is True
    assert checkpointer_policy_enabled(None) is False
    assert checkpointer_policy_enabled("off") is False
    assert checkpointer_policy_enabled("false") is False


@pytest.mark.asyncio
async def test_open_sqlite_checkpointer_opens_db(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import flowjet.core.agent.workspace as workspace_mod
    from flowjet.core.agent.workspace import Checkpointers

    db_path = tmp_path / "checkpoints.db"
    monkeypatch.setattr(
        workspace_mod, "resolve_checkpointer", lambda _cfg: (object(), str(db_path))
    )

    class FakeSaver:
        def __init__(self, conn: object, serde: object = None) -> None:
            self.conn = conn
            self.setup_called = False

        async def setup(self) -> None:
            self.setup_called = True

    class FakeConn:
        def __init__(self) -> None:
            self.closed = False
            self.pragmas: list[str] = []

        async def execute(self, sql: str) -> None:
            self.pragmas.append(sql)

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
    import soothe_nano.utils.serde as serde_mod

    monkeypatch.setattr(aiosqlite, "connect", fake_connect)
    monkeypatch.setattr(aio_mod, "AsyncSqliteSaver", fake_saver)
    monkeypatch.setattr(serde_mod, "create_soothe_serde", lambda: object())

    async with Checkpointers.open_sqlite(SootheConfig()) as cp:
        assert cp is savers[0]
        assert savers[0].setup_called is True
    assert fake_conn.closed is True
    # WAL + busy_timeout are set so pool workers can share the file.
    assert any("journal_mode=WAL" in p for p in fake_conn.pragmas)
    assert any("busy_timeout" in p for p in fake_conn.pragmas)


@pytest.mark.asyncio
async def test_build_agent_wires_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    import flowjet.cli.agent as agent_mod

    captured: dict[str, object] = {}

    class FakeGraph:
        def __init__(self) -> None:
            self.checkpointer = None

    class FakeAgent:
        def __init__(self) -> None:
            self.graph = FakeGraph()

    def fake_create(_cfg: object, _profile: object = None, **kwargs: object) -> FakeAgent:
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(agent_mod, "configure_cli_logging", lambda **_k: None)
    monkeypatch.setattr(agent_mod, "ensure_workspace", lambda _w=None: Path.cwd())
    monkeypatch.setattr(agent_mod, "create_agent", fake_create)
    monkeypatch.setattr(agent_mod, "silence_after_plugins", lambda **_k: None)

    cp = object()
    agent = await agent_mod.build_agent(SootheConfig(), checkpointer=cp, verbose=True)
    assert isinstance(agent, FakeAgent)
    # The checkpointer is a build-time parameter (not a post-hoc graph patch),
    # so every lazily compiled mode graph receives it.
    assert captured.get("checkpointer") is cp


@pytest.mark.asyncio
async def test_build_agent_ask_mode_forwards_interaction_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ask_mode=True must forward interaction_mode="ask" to create_nano_agent.

    soothe-nano 1.1.1's builder now owns the ask-mode surface natively:
    read-only filesystem tools, ask policy profile, and ask system prompt.
    fj no longer re-implements these; it just selects the mode.
    """
    import flowjet.cli.agent as agent_mod

    captured: dict[str, object] = {}

    class FakeGraph:
        checkpointer = None

    class FakeAgent:
        def __init__(self) -> None:
            self.graph = FakeGraph()

    def fake_create(_cfg: object, _profile: object = None, **kwargs: object) -> FakeAgent:
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(agent_mod, "configure_cli_logging", lambda **_k: None)
    monkeypatch.setattr(agent_mod, "ensure_workspace", lambda _w=None: Path.cwd())
    monkeypatch.setattr(agent_mod, "create_agent", fake_create)
    monkeypatch.setattr(agent_mod, "silence_after_plugins", lambda **_k: None)

    await agent_mod.build_agent(SootheConfig(), ask_mode=True)
    # The native ask mode must be selected; no hand-built ask policy is forwarded.
    assert captured.get("interaction_mode") == "ask"
    assert captured.get("policy") is None


# ---------------------------------------------------------------------------
# Ask mode
# ---------------------------------------------------------------------------


def test_apply_fj_defaults_preserves_sqlite_persistence_in_ask_context() -> None:
    """fj defaults force sqlite; ask mode no longer layers its own config on top,
    so this just re-checks the sqlite default is honored for the ask path too."""
    cfg = SootheConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": cfg.persistence.model_copy(update={"default_backend": "postgresql"}),
        }
    )
    forced = apply_fj_defaults(cfg)
    assert forced.resolve_checkpointer_backend() == "sqlite"


# ---------------------------------------------------------------------------
# Bypass mode (CLI default)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_agent_bypass_is_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI defaults to bypass mode — no flag needed to opt in.

    Bypass mode skips all security enforcement layers; the nano builder handles
    the policy profile and system prompt natively. fj only selects the mode.
    """
    import flowjet.cli.agent as agent_mod

    captured: dict[str, object] = {}

    class FakeGraph:
        checkpointer = None

    class FakeAgent:
        def __init__(self) -> None:
            self.graph = FakeGraph()

    def fake_create(_cfg: object, _profile: object = None, **kwargs: object) -> FakeAgent:
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(agent_mod, "configure_cli_logging", lambda **_k: None)
    monkeypatch.setattr(agent_mod, "ensure_workspace", lambda _w=None: Path.cwd())
    monkeypatch.setattr(agent_mod, "create_agent", fake_create)
    monkeypatch.setattr(agent_mod, "silence_after_plugins", lambda **_k: None)

    await agent_mod.build_agent(SootheConfig())
    assert captured.get("interaction_mode") == "bypass"
    assert captured.get("policy") is None
