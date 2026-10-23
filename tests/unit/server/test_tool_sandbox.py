"""ArcBox tool sandbox — nano.yml parsing, manager lifecycle, staging, adapter binding."""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import AsyncIterator, Callable
from pathlib import Path, PurePosixPath
from typing import ClassVar, cast

import pytest

from flowjet.core.sandbox import (
    ArcBoxToolSandboxManager,
    SandboxAwareWorkspaceResolver,
    SandboxSettingsLoader,
    ToolSandboxSettings,
)
from flowjet.server.config import Settings

# ---------------------------------------------------------------------------
# Fake arcbox SDK
# ---------------------------------------------------------------------------


class FakeEntry:
    def __init__(self, name: str, kind: str) -> None:
        self.name: str = name
        self.kind: str = kind


class FakeFiles:
    def __init__(self, tree: dict[str, bytes]) -> None:
        self.tree: dict[str, bytes] = tree
        self.write_calls: list[str] = []

    async def mkdir(self, path: PurePosixPath | str) -> None:
        _ = self.tree.setdefault(str(path) + "/.dir", b"")

    async def write_bytes(self, path: PurePosixPath | str, data: bytes) -> None:
        self.tree[str(path)] = bytes(data)
        self.write_calls.append(str(path))

    async def list(self, path: PurePosixPath | str) -> list[FakeEntry]:
        prefix = str(path).rstrip("/") + "/"
        children: dict[str, str] = {}
        for name in self.tree:
            if not name.startswith(prefix) or name.endswith("/.dir"):
                continue
            rest = name[len(prefix) :]
            head = rest.split("/", 1)[0]
            children[prefix + head] = "directory" if "/" in rest else "file"
        return [FakeEntry(name, kind) for name, kind in children.items()]

    async def read_bytes(self, path: PurePosixPath | str) -> bytes:
        return self.tree[str(path)]


class FakeSandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.id: str = sandbox_id
        self.files: FakeFiles = FakeFiles({})
        self.killed: bool = False

    async def kill(self) -> None:
        self.killed = True


class FakeConnection:
    def __init__(self, **kwargs: str) -> None:
        self.kwargs: dict[str, str] = kwargs


class FakeAsyncArcBox:
    instances: ClassVar[list[FakeAsyncArcBox]] = []

    def __init__(self, connection: FakeConnection | None = None) -> None:
        self.connection: FakeConnection | None = connection
        self.create_calls: list[dict[str, str | int | bool]] = []
        self.sandboxes: list[FakeSandbox] = []
        self.closed: bool = False
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
    setattr(module, "Connection", FakeConnection)
    setattr(module, "AsyncArcBox", FakeAsyncArcBox)
    monkeypatch.setitem(sys.modules, "arcbox", module)
    return FakeAsyncArcBox


def make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    _ = (ws / "a.txt").write_text("alpha")
    _ = (ws / "sub" / "b.txt").write_text("beta")
    (ws / "__pycache__").mkdir()
    _ = (ws / "__pycache__" / "junk.pyc").write_text("junk")
    return ws


# ---------------------------------------------------------------------------
# nano.yml sandbox section parsing
# ---------------------------------------------------------------------------


def test_parse_defaults_to_disabled() -> None:
    assert SandboxSettingsLoader.parse_section(None).enabled is False
    assert SandboxSettingsLoader.parse_section("nonsense").enabled is False
    assert SandboxSettingsLoader.parse_section({}).enabled is False


def test_network_defaults_to_off() -> None:
    """Guest egress is opt-in: `true` exposes the host's whole routing table."""
    assert ToolSandboxSettings().network is False
    assert SandboxSettingsLoader.parse_section({"enabled": True, "image": "img"}).network is False
    # Explicit opt-in still works.
    assert SandboxSettingsLoader.parse_section({"network": True}).network is True


def test_parse_reads_flowjet_keys_and_ignores_nano_keys() -> None:
    settings = SandboxSettingsLoader.parse_section(
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
    "factory",
    [
        lambda: ToolSandboxSettings(enabled=True),  # no image
        lambda: ToolSandboxSettings(enabled=True, image="   "),
        lambda: ToolSandboxSettings(vcpus=0),
        lambda: ToolSandboxSettings(mem_mib=64),
        lambda: ToolSandboxSettings(max_sandboxes=-1),
    ],
)
def test_parse_rejects_invalid_settings(factory: Callable[[], ToolSandboxSettings]) -> None:
    with pytest.raises(ValueError):
        _ = factory()


def test_parse_max_sandboxes_none_maps_to_none() -> None:
    """``max_sandboxes: none`` in YAML maps to ``None`` for compute-sizing."""
    settings = SandboxSettingsLoader.parse_section(
        {"enabled": True, "image": "img:1", "max_sandboxes": "none"}
    )
    assert settings.max_sandboxes is None


def test_parse_max_sandboxes_zero_means_unlimited() -> None:
    """``max_sandboxes: 0`` means unlimited (no LRU eviction)."""
    settings = SandboxSettingsLoader.parse_section(
        {"enabled": True, "image": "img:1", "max_sandboxes": 0}
    )
    assert settings.max_sandboxes == 0
    assert settings.effective_max_sandboxes() == 0


def test_parse_max_sandboxes_numeric_string_zero() -> None:
    """A numeric string ``"0"`` is coerced to int 0 (unlimited)."""
    settings = SandboxSettingsLoader.parse_section(
        {"enabled": True, "image": "img:1", "max_sandboxes": "0"}
    )
    assert settings.max_sandboxes == 0


def test_parse_max_sandboxes_explicit_int_preserved() -> None:
    """An explicit int ``max_sandboxes`` is preserved as-is (back-compat)."""
    settings = SandboxSettingsLoader.parse_section(
        {"enabled": True, "image": "img:1", "max_sandboxes": 3}
    )
    assert settings.max_sandboxes == 3


def test_parse_max_sandboxes_numeric_string_accepted() -> None:
    """A numeric string (e.g. from YAML without quotes) is coerced to int."""
    settings = SandboxSettingsLoader.parse_section(
        {"enabled": True, "image": "img:1", "max_sandboxes": "5"}
    )
    assert settings.max_sandboxes == 5


def test_effective_max_sandboxes_explicit() -> None:
    """When ``max_sandboxes`` is an explicit int, ``effective_`` returns it."""
    settings = ToolSandboxSettings(enabled=True, image="img:1", max_sandboxes=4)
    assert settings.effective_max_sandboxes() == 4


def test_effective_max_sandboxes_compute_from_cpu() -> None:
    """None mode computes cap from 70% usable CPU ÷ vcpus, min 8."""
    # 16 cores × 0.70 = 11 usable; 11 // 2 = 5 → floored to 8.
    settings = ToolSandboxSettings(enabled=True, image="img:1", vcpus=2, max_sandboxes=None)
    assert settings.effective_max_sandboxes(cpu_count=16) == 8

    # 32 cores × 0.70 = 22 usable; 22 // 2 = 11 → 11 (above min).
    assert settings.effective_max_sandboxes(cpu_count=32) == 11

    # 32 cores × 0.70 = 22 usable; 22 // 4 = 5 → floored to 8.
    settings_4vcpu = ToolSandboxSettings(enabled=True, image="img:1", vcpus=4, max_sandboxes=None)
    assert settings_4vcpu.effective_max_sandboxes(cpu_count=32) == 8


def test_effective_max_sandboxes_compute_min_floor() -> None:
    """Even a tiny host gets the minimum cap of 8."""
    settings = ToolSandboxSettings(enabled=True, image="img:1", vcpus=2, max_sandboxes=None)
    assert settings.effective_max_sandboxes(cpu_count=1) == 8


def test_effective_max_sandboxes_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``FLOWJET_SANDBOX_MAX`` env var overrides the YAML value."""
    settings = ToolSandboxSettings(enabled=True, image="img:1", max_sandboxes=None)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "5")
    assert settings.effective_max_sandboxes(cpu_count=32) == 5


def test_effective_max_sandboxes_env_override_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """``FLOWJET_SANDBOX_MAX=0`` means unlimited via env override."""
    settings = ToolSandboxSettings(enabled=True, image="img:1", max_sandboxes=4)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "0")
    assert settings.effective_max_sandboxes() == 0


def test_effective_max_sandboxes_env_override_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """``FLOWJET_SANDBOX_MAX=none`` defers to compute-sizing even if YAML pins a value."""
    settings = ToolSandboxSettings(enabled=True, image="img:1", vcpus=2, max_sandboxes=4)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "none")
    assert settings.effective_max_sandboxes(cpu_count=32) == 11


def test_effective_max_sandboxes_env_override_falls_back_on_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unparseable env value falls back to the YAML field."""
    settings = ToolSandboxSettings(enabled=True, image="img:1", max_sandboxes=3)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "garbage")
    assert settings.effective_max_sandboxes() == 3


def test_effective_max_sandboxes_env_percent_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``FLOWJET_SANDBOX_MAX_PERCENT`` tunes the CPU usable fraction (default 70)."""
    settings = ToolSandboxSettings(enabled=True, image="img:1", vcpus=2, max_sandboxes=None)
    # 32 cores × 0.50 = 16 usable; 16 // 2 = 8 → floored to 8.
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "50")
    assert settings.effective_max_sandboxes(cpu_count=32) == 8
    # 32 cores × 0.90 = 28 usable; 28 // 2 = 14 → 14 (above min).
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "90")
    assert settings.effective_max_sandboxes(cpu_count=32) == 14


def test_effective_max_sandboxes_env_percent_invalid_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An out-of-range percentage falls back to the 70% default."""
    settings = ToolSandboxSettings(enabled=True, image="img:1", vcpus=2, max_sandboxes=None)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "150")
    # 32 × 0.70 = 22; 22 // 2 = 11
    assert settings.effective_max_sandboxes(cpu_count=32) == 11


def test_load_settings_requires_existing_explicit_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _ = SandboxSettingsLoader.load(tmp_path / "missing.yml")


def test_load_settings_from_explicit_path(tmp_path: Path) -> None:
    path = tmp_path / "nano.yml"
    _ = path.write_text(
        "models:\n  default: gpt-x\nsandbox:\n  enabled: true\n  image: img:1\n  vcpus: 3\n",
        encoding="utf-8",
    )
    settings = SandboxSettingsLoader.load(path)
    assert settings.enabled is True
    assert settings.image == "img:1"
    assert settings.vcpus == 3


def test_load_settings_from_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import flowjet.home

    default = tmp_path / "nano.yml"
    monkeypatch.setattr(flowjet.home, "default_config_path", lambda: default)

    assert SandboxSettingsLoader.load(None).enabled is False  # no file at all

    _ = default.write_text("sandbox:\n  enabled: true\n  image: img\n", encoding="utf-8")
    settings = SandboxSettingsLoader.load(None)
    assert settings.enabled is True and settings.image == "img"


def test_load_settings_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "nano.yml"
    _ = path.write_text("sandbox: [unclosed", encoding="utf-8")
    with pytest.raises(ValueError):
        _ = SandboxSettingsLoader.load(path)


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
                "network": False,  # default: guest has no network at all
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
        _ = (ws / "a.txt").write_text("alpha-2")
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
        _ = (ws / "a.txt").write_text("peer-active")

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
async def test_close_propagates_guest_deletions_to_host(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    """A file the agent deleted inside the guest is removed from the host (RFC-RD-607 §4.4)."""
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(ToolSandboxSettings(enabled=True, image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        sandbox = fake_arcbox.instances[0].sandboxes[0]
        # Agent deleted sub/b.txt inside the guest.
        _ = sandbox.files.tree.pop("/workspace/sub/b.txt")

        await manager.close_workspace(str(ws))
        assert not (ws / "sub" / "b.txt").exists()
        assert not (ws / "sub").exists()  # emptied parent pruned
        assert (ws / "a.txt").read_text() == "alpha"  # untouched file survives
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_pull_never_deletes_host_files_added_after_push(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    """Host files created after the push are not in the manifest — never deleted."""
    ws = make_workspace(tmp_path)
    manager = ArcBoxToolSandboxManager(ToolSandboxSettings(enabled=True, image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        sandbox = fake_arcbox.instances[0].sandboxes[0]
        _ = sandbox.files.tree.pop("/workspace/a.txt")
        # Host-side addition between push and pull (e.g. a synced-in material).
        new_dir = ws / "materials" / "m1"
        new_dir.mkdir(parents=True)
        _ = (new_dir / "new.txt").write_text("fresh")

        await manager.close_workspace(str(ws))
        assert not (ws / "a.txt").exists()  # guest deletion propagated
        assert (new_dir / "new.txt").read_text() == "fresh"  # post-push host file survives
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


@pytest.mark.usefixtures("fake_arcbox")
@pytest.mark.asyncio
async def test_backend_for_binds_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("soothe_nano")
    import importlib

    sandbox_module = importlib.import_module("soothe_nano.sandbox")

    captured: list[dict[str, object]] = []

    class FakeArcBoxBackend:
        def __init__(self, **kwargs: object) -> None:
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
        backend = cast(object, manager.backend_for(str(ws)))
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
        assert cast(object, manager.backend_for(str(ws))) is backend  # cached per lease
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
async def test_max_sandboxes_zero_means_unlimited(
    fake_arcbox: type[FakeAsyncArcBox], tmp_path: Path
) -> None:
    """``max_sandboxes: 0`` disables LRU eviction — all idle sandboxes stay."""
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    manager = ArcBoxToolSandboxManager(
        ToolSandboxSettings(enabled=True, image="img:1", max_sandboxes=0)
    )
    try:
        await manager.open_workspace(str(ws1))
        sandbox1 = fake_arcbox.instances[0].sandboxes[0]
        await manager.close_workspace(str(ws1))
        await manager.open_workspace(str(ws2))
        assert not sandbox1.killed  # NOT evicted — unlimited
        assert manager.lease_count == 2
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_idle_reaper_kills_stale_sandboxes(
    fake_arcbox: type[FakeAsyncArcBox],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flowjet.core.sandbox.arbox as arbox_mod

    monkeypatch.setattr(arbox_mod, "_REAPER_INTERVAL_SECONDS", 0.05)
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

    def resolve(self, _session: str, _metadata: dict[str, object] | None = None) -> Path:
        return Path("/tmp/rec-ws")

    async def open_session(self, _session: str, _workspace: Path) -> None:
        self.calls.append("inner-open")

    async def close_session(self, _session: str, _workspace: Path) -> None:
        self.calls.append("inner-close")

    async def shutdown(self) -> None:
        self.calls.append("inner-shutdown")


class RecordingManager:
    """Duck-typed stand-in that only records lifecycle calls."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def open_workspace(self, _workspace: str) -> None:
        self.calls.append("manager-open")

    async def close_workspace(self, _workspace: str) -> None:
        self.calls.append("manager-close")

    async def shutdown(self) -> None:
        self.calls.append("manager-shutdown")


@pytest.mark.asyncio
async def test_resolver_orders_staging_around_sync_lifecycle() -> None:
    inner = RecordingResolver()
    fake_manager = RecordingManager()
    manager = cast(ArcBoxToolSandboxManager, cast(object, fake_manager))
    resolver = SandboxAwareWorkspaceResolver(inner, manager)

    assert resolver.resolve("s") == Path("/tmp/rec-ws")

    await resolver.open_session("s", Path("/tmp/rec-ws"))
    await resolver.close_session("s", Path("/tmp/rec-ws"))
    await resolver.shutdown()
    # Open: sync materializes first, then push into the guest.
    # Close: guest pull first, then the sync checkpoint sees the outputs.
    assert inner.calls == ["inner-open", "inner-close", "inner-shutdown"]
    assert fake_manager.calls == [
        "manager-open",
        "manager-close",
        "manager-shutdown",
    ]


def test_resolver_delegates_unknown_attributes() -> None:
    class Inner:
        marker: str = "delegated"

    resolver = SandboxAwareWorkspaceResolver(
        Inner(),
        cast(ArcBoxToolSandboxManager, cast(object, RecordingManager())),
    )
    assert cast(str, resolver.marker) == "delegated"


# ---------------------------------------------------------------------------
# Adapter binding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nano_adapter_binds_sandbox_and_uses_guest_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("langchain_core", reason="nano extra not installed")
    from langchain_core.messages import AIMessage

    from flowjet.core.bridges import base as bridge_base
    from flowjet.core.bridges.nano.adapter import NanoAgentAdapter
    from flowjet.core.events import RunCompleted
    from flowjet.core.runtime.isolation.request import IsolatedRunRequest

    class StubAgent:
        def __init__(self) -> None:
            self.last_config: dict[str, object] | None = None

        async def astream(
            self, _input: object, **kwargs: object
        ) -> AsyncIterator[tuple[str, str, tuple[AIMessage, dict[str, object]]]]:
            self.last_config = cast("dict[str, object] | None", kwargs.get("config"))
            yield ("ns", "messages", (AIMessage(content="ok"), {}))

    built: list[dict[str, object | None]] = []
    agents: list[StubAgent] = []

    def fake_create(
        _config_path: str | Path | None,
        *,
        sandbox: object | None = None,
        checkpointer: object | None = None,
    ) -> StubAgent:
        built.append({"sandbox": sandbox, "checkpointer": checkpointer})
        agent = StubAgent()
        agents.append(agent)
        return agent

    monkeypatch.setattr(bridge_base, "create_server_agent_instance", fake_create)

    class FakeManager:
        guest_workspace: str = "/workspace"

        def __init__(self) -> None:
            self.backends: dict[str, object] = {str(tmp_path): object()}

        def backend_for(self, workspace: str) -> object:
            return self.backends[workspace]

    fake_manager = FakeManager()
    manager = cast(ArcBoxToolSandboxManager, cast(object, fake_manager))
    adapter = NanoAgentAdapter(sandbox_manager=manager)

    req = IsolatedRunRequest(
        run_id="r1",
        session="s1",
        input_text="hi",
        model="default",
        workspace=tmp_path,
    )
    events = [event async for event in adapter.astream(req)]
    completed = [e for e in events if isinstance(e, RunCompleted)]
    assert any(e.output_text == "ok" for e in completed)
    assert built == [{"sandbox": fake_manager.backends[str(tmp_path)], "checkpointer": None}]

    agent = agents[0]
    assert agent.last_config is not None
    config = agent.last_config
    configurable = cast("dict[str, object]", config["configurable"])
    assert configurable["workspace"] == "/workspace"

    # Same workspace reuses the agent; a different one rebuilds.
    req2 = IsolatedRunRequest(
        run_id="r2",
        session="s2",
        input_text="hi",
        model="default",
        workspace=tmp_path / "other",
    )
    fake_manager.backends[str(tmp_path / "other")] = object()
    events = [event async for event in adapter.astream(req2)]
    assert len(events) >= 1
    assert len(built) == 2
    assert adapter.generation == 2


# ---------------------------------------------------------------------------
# Server wiring
# ---------------------------------------------------------------------------


def _settings_for(tmp_path: Path, nano_yml: str) -> Settings:
    path = tmp_path / "nano.yml"
    _ = path.write_text(nano_yml, encoding="utf-8")
    return Settings(home=str(tmp_path / "home"), models="default", nano_config=str(path))


def test_build_sandbox_manager_disabled_by_default(tmp_path: Path) -> None:
    from flowjet.server.http.app import build_sandbox_manager

    settings = _settings_for(tmp_path, "models:\n  default: gpt-x\n")
    assert build_sandbox_manager(settings) is None


@pytest.mark.usefixtures("fake_arcbox")
def test_build_sandbox_manager_enabled(tmp_path: Path) -> None:
    from flowjet.server.http.app import build_sandbox_manager, build_workspace_resolver

    settings = _settings_for(
        tmp_path,
        "sandbox:\n  enabled: true\n  image: flowjet-server:latest\n",
    )
    manager = build_sandbox_manager(settings)
    assert manager is not None
    assert manager.settings.image == "flowjet-server:latest"

    # Without workspace sync the local resolver is wrapped for staging.
    resolver = build_workspace_resolver(settings, manager)
    assert isinstance(resolver, SandboxAwareWorkspaceResolver)

    # Sandbox config missing an image fails loud at startup.
    bad = _settings_for(tmp_path, "sandbox:\n  enabled: true\n")
    with pytest.raises(ValueError, match="sandbox.image"):
        _ = build_sandbox_manager(bad)
