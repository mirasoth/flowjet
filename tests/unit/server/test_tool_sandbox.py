"""ArcBox tool sandbox — nano.yml parsing, manager lifecycle, staging, adapter binding."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from flowjet.core.backends.tool_sandbox import (
    ArcBoxToolSandboxManager,
    SandboxAwareWorkspaceResolver,
    ToolSandboxSettings,
    load_tool_sandbox_settings,
    parse_sandbox_section,
)

# ---------------------------------------------------------------------------
# Fake arcbox SDK
# ---------------------------------------------------------------------------


class FakeEntry:
    def __init__(self, name: str, kind: str) -> None:
        self.name = name
        self.kind = kind


class FakeFiles:
    def __init__(self, tree: dict[str, bytes]) -> None:
        self.tree = tree
        self.write_calls: list[str] = []

    async def mkdir(self, path: Any) -> None:
        self.tree.setdefault(str(path) + "/.dir", b"")

    async def write_bytes(self, path: Any, data: bytes) -> None:
        self.tree[str(path)] = bytes(data)
        self.write_calls.append(str(path))

    async def list(self, path: Any) -> list[FakeEntry]:
        prefix = str(path).rstrip("/") + "/"
        children: dict[str, str] = {}
        for name in self.tree:
            if not name.startswith(prefix) or name.endswith("/.dir"):
                continue
            rest = name[len(prefix) :]
            head = rest.split("/", 1)[0]
            children[prefix + head] = "directory" if "/" in rest else "file"
        return [FakeEntry(name, kind) for name, kind in children.items()]

    async def read_bytes(self, path: Any) -> bytes:
        return self.tree[str(path)]


class FakeSandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.id = sandbox_id
        self.files = FakeFiles({})
        self.killed = False

    async def kill(self) -> None:
        self.killed = True


class FakeAsyncArcBox:
    instances: list[FakeAsyncArcBox] = []

    def __init__(self, connection: Any = None) -> None:
        self.connection = connection
        self.create_calls: list[dict[str, Any]] = []
        self.sandboxes: list[FakeSandbox] = []
        self.closed = False
        FakeAsyncArcBox.instances.append(self)

    async def create(
        self,
        template: str,
        *,
        vcpus: int,
        memory_mib: int,
        network: bool,
        wait_until_ready: bool,
    ) -> FakeSandbox:
        self.create_calls.append(
            {
                "template": template,
                "vcpus": vcpus,
                "memory_mib": memory_mib,
                "network": network,
                "wait_until_ready": wait_until_ready,
            }
        )
        sandbox = FakeSandbox(f"sbx-{len(self.sandboxes)}")
        self.sandboxes.append(sandbox)
        return sandbox

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture()
def fake_arcbox(monkeypatch: pytest.MonkeyPatch) -> type[FakeAsyncArcBox]:
    FakeAsyncArcBox.instances = []
    module = types.ModuleType("arcbox")

    class Connection:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    setattr(module, "Connection", Connection)
    setattr(module, "AsyncArcBox", FakeAsyncArcBox)
    monkeypatch.setitem(sys.modules, "arcbox", module)
    return FakeAsyncArcBox


def make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    (ws / "a.txt").write_text("alpha")
    (ws / "sub" / "b.txt").write_text("beta")
    (ws / "__pycache__").mkdir()
    (ws / "__pycache__" / "junk.pyc").write_text("junk")
    return ws


# ---------------------------------------------------------------------------
# nano.yml sandbox section parsing
# ---------------------------------------------------------------------------


def test_parse_defaults_to_disabled() -> None:
    assert parse_sandbox_section(None).enabled is False
    assert parse_sandbox_section("nonsense").enabled is False
    assert parse_sandbox_section({}).enabled is False


def test_parse_reads_flowjet_keys_and_ignores_nano_keys() -> None:
    settings = parse_sandbox_section(
        {
            "enabled": True,
            "image": "flowjet-server:latest",
            "vcpus": 4,
            "mem_mib": 4096,
            "network": False,
            "workspace_root": "/data",
            "default_timeout": 30,
            "idle_timeout_seconds": 60,
            "max_sandboxes": 2,
            # nano-owned placement policy keys must be ignored here.
            "on_deny": "drop",
            "placement_overrides": {"mcp": "host"},
            "max_shuttle_bytes": 1024,
        }
    )
    assert settings.enabled is True
    assert settings.image == "flowjet-server:latest"
    assert settings.vcpus == 4
    assert settings.mem_mib == 4096
    assert settings.network is False
    assert settings.workspace_root == "/data"
    assert settings.default_timeout == 30
    assert settings.idle_timeout_seconds == 60
    assert settings.max_sandboxes == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": True},  # no image
        {"enabled": True, "image": "   "},
        {"vcpus": 0},
        {"mem_mib": 64},
        {"max_sandboxes": 0},
    ],
)
def test_parse_rejects_invalid_settings(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ToolSandboxSettings(**overrides)


def test_load_settings_requires_existing_explicit_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_tool_sandbox_settings(tmp_path / "missing.yml")


def test_load_settings_from_explicit_path(tmp_path: Path) -> None:
    path = tmp_path / "nano.yml"
    path.write_text(
        "models:\n  default: gpt-x\nsandbox:\n  enabled: true\n  image: img:1\n  vcpus: 3\n",
        encoding="utf-8",
    )
    settings = load_tool_sandbox_settings(path)
    assert settings.enabled is True
    assert settings.image == "img:1"
    assert settings.vcpus == 3


def test_load_settings_from_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import flowjet.home

    default = tmp_path / "nano.yml"
    monkeypatch.setattr(flowjet.home, "default_config_path", lambda: default)

    assert load_tool_sandbox_settings(None).enabled is False  # no file at all

    default.write_text("sandbox:\n  enabled: true\n  image: img\n", encoding="utf-8")
    settings = load_tool_sandbox_settings(None)
    assert settings.enabled is True and settings.image == "img"


def test_load_settings_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "nano.yml"
    path.write_text("sandbox: [unclosed", encoding="utf-8")
    with pytest.raises(ValueError):
        load_tool_sandbox_settings(path)


# ---------------------------------------------------------------------------
# Manager: spawn, staging, backend binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_spawns_sandbox_and_pushes_workspace(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(
        ToolSandboxSettings(enabled=True, image="img:1", vcpus=3, mem_mib=512)
    )
    try:
        await manager.open_workspace(str(ws))
        client = fake_arcbox.instances[0]
        assert client.create_calls == [
            {
                "template": "img:1",
                "vcpus": 3,
                "memory_mib": 512,
                "network": True,
                "wait_until_ready": True,
            }
        ]
        tree = client.sandboxes[0].files.tree
        assert tree["/workspace/a.txt"] == b"alpha"
        assert tree["/workspace/sub/b.txt"] == b"beta"
        assert not any("__pycache__" in name for name in tree)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_reopen_without_changes_skips_push(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(ToolSandboxSettings(enabled=True, image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        await manager.close_workspace(str(ws))
        await manager.close_workspace(str(ws))  # unbalanced close: no-op
        files = fake_arcbox.instances[0].sandboxes[0].files
        files.write_calls.clear()

        await manager.open_workspace(str(ws))  # manifest matches: no push
        assert files.write_calls == []
        await manager.close_workspace(str(ws))

        # Host-side change between sessions (e.g. new material synced in):
        # the next open pushes exactly the changed file.
        (ws / "a.txt").write_text("alpha-2")
        await manager.open_workspace(str(ws))
        assert files.write_calls == ["/workspace/a.txt"]
        assert files.tree["/workspace/a.txt"] == b"alpha-2"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_second_concurrent_open_skips_push(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(ToolSandboxSettings(enabled=True, image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        files = fake_arcbox.instances[0].sandboxes[0].files
        files.write_calls.clear()
        (ws / "a.txt").write_text("peer-active")

        # A peer session is mid-run: the push must not clobber live guest state.
        await manager.open_workspace(str(ws))
        assert files.write_calls == []
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_close_pulls_guest_changes_back_to_host(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(ToolSandboxSettings(enabled=True, image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        sandbox = fake_arcbox.instances[0].sandboxes[0]
        # Agent wrote a new file and modified an existing one in the guest.
        sandbox.files.tree["/workspace/out/report.md"] = b"# done"
        sandbox.files.tree["/workspace/a.txt"] = b"alpha-2"

        await manager.close_workspace(str(ws))
        assert (ws / "out" / "report.md").read_bytes() == b"# done"
        assert (ws / "a.txt").read_text() == "alpha-2"
        # Unchanged file keeps its host mtime (no rewrite).
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_close_pulls_only_when_last_run_ends(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(ToolSandboxSettings(enabled=True, image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        await manager.open_workspace(str(ws))  # second active run
        sandbox = fake_arcbox.instances[0].sandboxes[0]
        sandbox.files.tree["/workspace/new.txt"] = b"new"

        await manager.close_workspace(str(ws))  # one run still active
        assert not (ws / "new.txt").exists()

        await manager.close_workspace(str(ws))  # last run: pull
        assert (ws / "new.txt").read_bytes() == b"new"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_backend_for_binds_and_caches(
    fake_arcbox: type[FakeAsyncArcBox],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("soothe_nano")
    import importlib

    sandbox_module = importlib.import_module("soothe_nano.sandbox")

    captured: list[dict[str, Any]] = []

    class FakeArcBoxBackend:
        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

    monkeypatch.setattr(sandbox_module, "ArcBoxBackend", FakeArcBoxBackend)

    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(
        ToolSandboxSettings(enabled=True, image="img:1", workspace_root="/data", default_timeout=42)
    )
    try:
        with pytest.raises(RuntimeError):
            manager.backend_for(str(ws))  # not opened yet

        await manager.open_workspace(str(ws))
        backend = manager.backend_for(str(ws))
        assert captured == [
            {
                "sandbox_id": "sbx-0",
                "workspace_root": "/data",
                "default_timeout": 42,
                "api_url": None,
                "api_key": None,
                "connect_timeout": 60.0,
            }
        ]
        assert manager.backend_for(str(ws)) is backend  # cached per lease
        assert manager.guest_workspace == "/data"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_max_sandboxes_evicts_idle_lru(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    manager = ArcBoxToolSandboxManager(
        ToolSandboxSettings(enabled=True, image="img:1", max_sandboxes=1)
    )
    try:
        await manager.open_workspace(str(ws1))
        sandbox1 = fake_arcbox.instances[0].sandboxes[0]
        await manager.close_workspace(str(ws1))
        await manager.open_workspace(str(ws2))
        assert sandbox1.killed  # evicted (idle, LRU)
        assert manager.lease_count == 1
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_idle_reaper_kills_stale_sandboxes(
    fake_arcbox: type[FakeAsyncArcBox],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flowjet.core.backends.tool_sandbox as ts

    monkeypatch.setattr(ts, "_REAPER_INTERVAL_SECONDS", 0.05)
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(
        ToolSandboxSettings(enabled=True, image="img:1", idle_timeout_seconds=0.01)
    )
    await manager.open_workspace(str(ws))
    sandbox = fake_arcbox.instances[0].sandboxes[0]
    await manager.close_workspace(str(ws))
    await asyncio.sleep(0.3)
    assert sandbox.killed
    assert manager.lease_count == 0
    await manager.shutdown()


@pytest.mark.asyncio
async def test_shutdown_kills_all_and_closes_client(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(ToolSandboxSettings(enabled=True, image="img:1"))
    await manager.open_workspace(str(ws))
    client = fake_arcbox.instances[0]
    await manager.shutdown()
    assert client.sandboxes[0].killed
    assert client.closed

    await manager.shutdown()  # idempotent


@pytest.mark.asyncio
async def test_validate_runtime_fails_without_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "arcbox", None)  # forces ImportError
    manager = ArcBoxToolSandboxManager(ToolSandboxSettings(enabled=True, image="img:1"))
    with pytest.raises(RuntimeError, match="arcbox SDK"):
        manager.validate_runtime()


# ---------------------------------------------------------------------------
# Resolver decorator: staging sandwiched into the session lifecycle
# ---------------------------------------------------------------------------


class RecordingResolver:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve(self, session: str, metadata: dict[str, Any] | None = None) -> Path:
        return Path("/tmp/rec-ws")

    async def open_session(self, session: str, workspace: Path) -> None:
        self.calls.append("inner-open")

    async def close_session(self, session: str, workspace: Path) -> None:
        self.calls.append("inner-close")

    async def shutdown(self) -> None:
        self.calls.append("inner-shutdown")


class RecordingManager(ArcBoxToolSandboxManager):
    def __init__(self) -> None:
        super().__init__(ToolSandboxSettings(enabled=True, image="img"))
        self.calls: list[str] = []

    async def open_workspace(self, workspace: str) -> None:
        self.calls.append("manager-open")

    async def close_workspace(self, workspace: str) -> None:
        self.calls.append("manager-close")

    async def shutdown(self) -> None:
        self.calls.append("manager-shutdown")


@pytest.mark.asyncio
async def test_resolver_orders_staging_around_sync_lifecycle() -> None:
    inner = RecordingResolver()
    manager = RecordingManager()
    resolver = SandboxAwareWorkspaceResolver(inner, manager)

    assert resolver.resolve("s") == Path("/tmp/rec-ws")

    await resolver.open_session("s", Path("/tmp/rec-ws"))
    await resolver.close_session("s", Path("/tmp/rec-ws"))
    await resolver.shutdown()
    # Open: sync materializes first, then push into the guest.
    # Close: guest pull first, then the sync checkpoint sees the outputs.
    assert inner.calls == ["inner-open", "inner-close", "inner-shutdown"]
    assert manager.calls == ["manager-open", "manager-close", "manager-shutdown"]


@pytest.mark.asyncio
async def test_resolver_delegates_unknown_attributes() -> None:
    class Inner:
        marker = "delegated"

    resolver = SandboxAwareWorkspaceResolver(Inner(), RecordingManager())
    assert resolver.marker == "delegated"


# ---------------------------------------------------------------------------
# Adapter binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nano_adapter_binds_sandbox_and_uses_guest_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("langchain_core", reason="nano extra not installed")
    from langchain_core.messages import AIMessage

    from flowjet.core.backends.isolation.request import IsolatedRunRequest
    from flowjet.core.bridges.nano import adapter as nano_adapter_module
    from flowjet.core.bridges.nano.adapter import NanoAgentAdapter

    class StubAgent:
        def __init__(self) -> None:
            self.last_config: dict[str, Any] | None = None

        async def astream(self, _input: Any, **kwargs: Any):
            self.last_config = kwargs.get("config")
            yield ("ns", "messages", (AIMessage(content="ok"), {}))

    built: list[dict[str, Any]] = []

    def fake_create(config_path: Any, *, sandbox: Any = None) -> StubAgent:
        built.append({"sandbox": sandbox})
        return StubAgent()

    monkeypatch.setattr(nano_adapter_module, "create_nano_agent_instance", fake_create)

    class FakeManager:
        guest_workspace = "/workspace"

        def __init__(self) -> None:
            self.backends: dict[str, Any] = {str(tmp_path): object()}

        def backend_for(self, workspace: str) -> Any:
            return self.backends[workspace]

    manager: Any = FakeManager()
    adapter = NanoAgentAdapter(sandbox_manager=manager)

    req = IsolatedRunRequest(
        run_id="r1",
        session="s1",
        input_text="hi",
        model="default",
        workspace=tmp_path,
    )
    events = [event async for event in adapter.astream(req)]
    from flowjet.core.events import RunCompleted

    completed = [e for e in events if isinstance(e, RunCompleted)]
    assert any(e.output_text == "ok" for e in completed)
    assert built == [{"sandbox": manager.backends[str(tmp_path)]}]

    agent = adapter._ensure(workspace=str(tmp_path))
    assert agent.last_config is not None
    assert agent.last_config["configurable"]["workspace"] == "/workspace"

    # Same workspace reuses the agent; a different one rebuilds.
    req2 = IsolatedRunRequest(
        run_id="r2",
        session="s2",
        input_text="hi",
        model="default",
        workspace=tmp_path / "other",
    )
    manager.backends[str(tmp_path / "other")] = object()
    events = [event async for event in adapter.astream(req2)]
    assert len(events) >= 1
    assert len(built) == 2
    assert adapter.generation == 2


# ---------------------------------------------------------------------------
# Server wiring
# ---------------------------------------------------------------------------


def _settings_for(tmp_path: Path, nano_yml: str) -> Any:
    from flowjet.server.config import Settings

    path = tmp_path / "nano.yml"
    path.write_text(nano_yml, encoding="utf-8")
    return Settings(home=str(tmp_path / "home"), models="default", nano_config=str(path))


def test_build_sandbox_manager_disabled_by_default(tmp_path: Path) -> None:
    from flowjet.server.http.app import _build_sandbox_manager

    settings = _settings_for(tmp_path, "models:\n  default: gpt-x\n")
    assert _build_sandbox_manager(settings) is None


def test_build_sandbox_manager_enabled(tmp_path: Path, fake_arcbox: type[FakeAsyncArcBox]) -> None:
    from flowjet.server.http.app import _build_sandbox_manager, _build_workspace_resolver

    settings = _settings_for(
        tmp_path,
        "sandbox:\n  enabled: true\n  image: flowjet-server:latest\n",
    )
    manager = _build_sandbox_manager(settings)
    assert manager is not None
    assert manager.settings.image == "flowjet-server:latest"

    # Without workspace sync the local resolver is wrapped for staging.
    resolver = _build_workspace_resolver(settings, manager)
    assert isinstance(resolver, SandboxAwareWorkspaceResolver)

    # Sandbox config missing an image fails loud at startup.
    bad = _settings_for(tmp_path, "sandbox:\n  enabled: true\n")
    with pytest.raises(ValueError, match="sandbox.image"):
        _build_sandbox_manager(bad)
