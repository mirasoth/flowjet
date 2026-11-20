"""Tool sandbox — nano.yml parsing, manager lifecycle, staging, adapter binding.

Tests mock soothe-nano's sandbox backend factory (``create_sandbox_backend``)
instead of any specific backend SDK: flowjet is backend-agnostic and delegates
construction to nano's factory. The factory is patched to return a fake whose
``execute`` / ``upload_files`` / ``download_files`` / ``free_space_bytes`` /
``id`` / ``close`` shape mirrors the real contract.
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar, cast

import pytest

from flowjet.core.sandbox import (
    SandboxAwareWorkspaceResolver,
    SandboxDiskFullError,
    SandboxSettingsLoader,
    ToolSandboxManager,
    ToolSandboxSettings,
)
from flowjet.server.config import Settings

# ---------------------------------------------------------------------------
# Helpers: build backend config dicts in the new multi-backend format
# ---------------------------------------------------------------------------


def _backend_cfg(
    *,
    image: str = "img:1",
    vcpus: int = 2,
    mem_mib: int = 2048,
    network: bool = False,
    workspace_root: str = "/workspace",
    default_timeout: int = 120,
    connect_timeout: float = 60.0,
    idle_timeout_seconds: float = 300.0,
    min_free_bytes: int = 0,
    api_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Build a ``sandbox.backend`` dict in the multi-backend config format."""
    arcbox: dict = {"image": image, "vcpus": vcpus, "mem_mib": mem_mib}
    if network:
        arcbox["network"] = True
    if workspace_root != "/workspace":
        arcbox["workspace_root"] = workspace_root
    if default_timeout != 120:
        arcbox["default_timeout"] = default_timeout
    if connect_timeout != 60.0:
        arcbox["connect_timeout"] = connect_timeout
    if idle_timeout_seconds != 300.0:
        arcbox["idle_timeout_seconds"] = idle_timeout_seconds
    if min_free_bytes != 0:
        arcbox["min_free_bytes"] = min_free_bytes
    if api_url is not None:
        arcbox["api_url"] = api_url
    if api_key is not None:
        arcbox["api_key"] = api_key
    return {"type": "arcbox", "arcbox": arcbox}


def _settings(
    *,
    enabled: bool = True,
    max_sandboxes: int | None = 8,
    idle_timeout_seconds: float = 300.0,
    min_free_bytes: int = 0,
    **backend_kwargs,
) -> ToolSandboxSettings:
    """Build ToolSandboxSettings with the new backend config format."""
    backend = _backend_cfg(
        idle_timeout_seconds=idle_timeout_seconds,
        min_free_bytes=min_free_bytes,
        **backend_kwargs,
    )
    return ToolSandboxSettings(
        enabled=enabled,
        backend=backend,
        max_sandboxes=max_sandboxes,
        idle_timeout_seconds=idle_timeout_seconds,
        min_free_bytes=min_free_bytes,
    )


# ---------------------------------------------------------------------------
# Fake sandbox backend (nano's execution surface)
# ---------------------------------------------------------------------------


class FakeArcBoxBackend:
    """Mock sandbox backend with an in-memory guest filesystem.

    Mirrors the real contract:
    - ``id``: lazily-assigned sandbox id (triggers "creation" on first access)
    - ``execute(command)``: runs a command against the in-memory tree
    - ``upload_files(files)``: writes files into the guest tree
    - ``download_files(paths)``: reads files from the guest tree
    - ``free_space_bytes()``: returns available space (configurable)
    - ``close()``: marks the backend as closed (sandbox destroyed)
    """

    _id_counter: ClassVar[int] = 0
    instances: ClassVar[list[FakeArcBoxBackend]] = []
    #: Class-level registry shared across all instances (simulates daemon state)
    registry: ClassVar[list[FakeArcBoxBackend]] = []

    def __init__(
        self,
        *,
        image: str = "",
        vcpus: int = 2,
        mem_mib: int = 2048,
        network: bool = False,
        workspace_root: str = "/workspace",
        default_timeout: int = 120,
        connect_timeout: float = 60.0,
        idle_timeout_seconds: float = 300.0,
        min_free_bytes: int = 0,
        api_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._image = image
        self._vcpus = vcpus
        self._mem_mib = mem_mib
        self._network = network
        self.workspace_root = workspace_root
        self.default_timeout = default_timeout
        self._connect_timeout = connect_timeout
        self._idle_timeout_seconds = idle_timeout_seconds
        self._min_free_bytes = min_free_bytes
        self._api_url = api_url
        self._api_key = api_key
        self._sandbox_id: str | None = None
        self.closed: bool = False
        self._free_space: int | None = 5 * 1024**3  # 5 GiB default
        #: In-memory guest filesystem: guest path -> bytes
        self.tree: dict[str, bytes] = {}
        #: Commands executed via execute()
        self.executed_commands: list[str] = []
        #: Files uploaded via upload_files()
        self.uploaded_files: list[str] = []
        FakeArcBoxBackend.instances.append(self)

    @property
    def id(self) -> str:
        """Lazily assign a sandbox id (simulates VM creation on first use)."""
        if self._sandbox_id is None:
            FakeArcBoxBackend._id_counter += 1
            self._sandbox_id = f"sbx-{FakeArcBoxBackend._id_counter}"
            FakeArcBoxBackend.registry.append(self)
        return self._sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> SimpleNamespace:
        self.executed_commands.append(command)
        # Handle mkdir -p
        if command.startswith("mkdir -p"):
            path = command.split("mkdir -p -- ", 1)[-1].strip("'\"")
            self.tree.setdefault(path + "/.dir", b"")
            return SimpleNamespace(output="", exit_code=0)
        # Handle find ... -type f -print0
        if command.startswith("find"):
            parts = command.split()
            find_root = parts[1] if len(parts) > 1 else "/"
            prefix = find_root.rstrip("/") + "/"
            files = [p for p in self.tree if p.startswith(prefix) and not p.endswith("/.dir")]
            output = "\0".join(files)
            return SimpleNamespace(output=output, exit_code=0)
        return SimpleNamespace(output="", exit_code=0)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[SimpleNamespace]:
        responses = []
        for path, data in files:
            if not path.startswith("/"):
                responses.append(SimpleNamespace(path=path, error="invalid_path"))
                continue
            self.tree[path] = bytes(data)
            self.uploaded_files.append(path)
            responses.append(SimpleNamespace(path=path, error=None))
        return responses

    def download_files(self, paths: list[str]) -> list[SimpleNamespace]:
        responses = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(SimpleNamespace(path=path, content=None, error="invalid_path"))
                continue
            if path in self.tree:
                responses.append(SimpleNamespace(path=path, content=self.tree[path], error=None))
            else:
                responses.append(SimpleNamespace(path=path, content=None, error="not_found"))
        return responses

    def free_space_bytes(self, path: str | None = None) -> int | None:
        return self._free_space

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> type[FakeArcBoxBackend]:
    """Patch nano's create_sandbox_backend factory to return FakeArcBoxBackend.

    The factory takes a ``SandboxBackendConfig`` and dispatches to the
    registered backend. We patch it to extract the ``arcbox`` sub-config and
    construct a ``FakeArcBoxBackend`` from its fields.
    """
    FakeArcBoxBackend._id_counter = 0
    FakeArcBoxBackend.instances = []
    FakeArcBoxBackend.registry = []

    def _fake_create(config):
        """Fake factory: extract arcbox config fields and build a FakeArcBoxBackend."""
        arcbox = getattr(config, "arcbox", None)
        if arcbox is None:
            # Try dict-like access for stub configs
            arcbox = config.get("arcbox") if isinstance(config, dict) else None
        if arcbox is None:
            msg = "sandbox.backend.type='arcbox' requires sandbox.backend.arcbox config"
            raise ValueError(msg)
        # Extract fields from the ArcBoxBackendConfig (Pydantic model or stub)
        kwargs = {}
        for field in (
            "image",
            "vcpus",
            "mem_mib",
            "network",
            "workspace_root",
            "default_timeout",
            "connect_timeout",
            "idle_timeout_seconds",
            "min_free_bytes",
            "api_url",
            "api_key",
        ):
            val = getattr(arcbox, field, None)
            if val is None and isinstance(arcbox, dict):
                val = arcbox.get(field)
            if val is not None:
                kwargs[field] = val
        return FakeArcBoxBackend(**kwargs)

    # Patch the factory function in nano's sandbox module.
    try:
        sandbox_module = __import__("soothe_nano.sandbox", fromlist=["create_sandbox_backend"])
        monkeypatch.setattr(sandbox_module, "create_sandbox_backend", _fake_create)
    except ImportError:
        # Create a minimal stub module so factory patching works even
        # without soothe-nano installed (CI without the extra).
        sandbox_module = types.ModuleType("soothe_nano.sandbox")
        sandbox_module.create_sandbox_backend = _fake_create
        sys.modules["soothe_nano.sandbox"] = sandbox_module

    # Also patch SandboxBackendConfig so _spawn can construct it without nano.
    try:
        config_models = __import__("soothe_nano.config.models", fromlist=["SandboxBackendConfig"])
        # Keep the real SandboxBackendConfig — it works with the fake factory.
    except ImportError:
        # Stub SandboxBackendConfig as a simple namespace that preserves kwargs.
        class _StubBackendConfig:
            def __init__(self, **kwargs):
                self.type = kwargs.get("type", "arcbox")
                self.arcbox = kwargs.get("arcbox")

        config_models = types.ModuleType("soothe_nano.config.models")
        config_models.SandboxBackendConfig = _StubBackendConfig
        sys.modules.setdefault("soothe_nano.config", types.ModuleType("soothe_nano.config"))
        sys.modules["soothe_nano.config.models"] = config_models

    return FakeArcBoxBackend


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
    settings = _settings()
    assert settings.network is False
    # Explicit opt-in still works.
    settings_net = _settings(network=True)
    assert settings_net.network is True


def test_disk_watermark_defaults_to_disabled() -> None:
    settings = _settings()
    assert settings.min_free_bytes == 0
    settings_wm = _settings(min_free_bytes=524288000)
    assert settings_wm.min_free_bytes == 524288000


def test_disk_watermark_negative_rejected() -> None:
    with pytest.raises(ValueError, match="min_free_bytes"):
        _ = _settings(min_free_bytes=-1)


def test_parse_reads_flowjet_keys_and_ignores_nano_keys() -> None:
    settings = SandboxSettingsLoader.parse_section(
        {
            "enabled": True,
            "backend": {
                "type": "arcbox",
                "arcbox": {
                    "image": "flowjet-server:latest",
                    "vcpus": 4,
                    "mem_mib": 4096,
                    "network": False,
                    "workspace_root": "/data",
                    "default_timeout": 30,
                },
            },
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
        lambda: _settings(image=""),  # empty image
        lambda: _settings(image="   "),  # whitespace image
        lambda: _settings(vcpus=0),  # invalid vcpus
        lambda: _settings(mem_mib=64),  # too little memory
        lambda: _settings(max_sandboxes=-1),  # negative cap
    ],
)
def test_parse_rejects_invalid_settings(factory: Callable[[], ToolSandboxSettings]) -> None:
    with pytest.raises(ValueError):
        _ = factory()


def test_parse_max_sandboxes_none_maps_to_none() -> None:
    """``max_sandboxes: none`` in YAML maps to ``None`` for compute-sizing."""
    settings = SandboxSettingsLoader.parse_section(
        {
            "enabled": True,
            "backend": _backend_cfg(),
            "max_sandboxes": "none",
        }
    )
    assert settings.max_sandboxes is None


def test_parse_max_sandboxes_zero_means_unlimited() -> None:
    """``max_sandboxes: 0`` means unlimited (no LRU eviction)."""
    settings = SandboxSettingsLoader.parse_section(
        {
            "enabled": True,
            "backend": _backend_cfg(),
            "max_sandboxes": 0,
        }
    )
    assert settings.max_sandboxes == 0
    assert settings.effective_max_sandboxes() == 0


def test_parse_max_sandboxes_numeric_string_zero() -> None:
    """A numeric string ``"0"`` is coerced to int 0 (unlimited)."""
    settings = SandboxSettingsLoader.parse_section(
        {
            "enabled": True,
            "backend": _backend_cfg(),
            "max_sandboxes": "0",
        }
    )
    assert settings.max_sandboxes == 0


def test_parse_max_sandboxes_explicit_int_preserved() -> None:
    """An explicit int ``max_sandboxes`` is preserved as-is."""
    settings = SandboxSettingsLoader.parse_section(
        {
            "enabled": True,
            "backend": _backend_cfg(),
            "max_sandboxes": 3,
        }
    )
    assert settings.max_sandboxes == 3


def test_parse_max_sandboxes_numeric_string_accepted() -> None:
    """A numeric string (e.g. from YAML without quotes) is coerced to int."""
    settings = SandboxSettingsLoader.parse_section(
        {
            "enabled": True,
            "backend": _backend_cfg(),
            "max_sandboxes": "5",
        }
    )
    assert settings.max_sandboxes == 5


def test_effective_max_sandboxes_explicit() -> None:
    """When ``max_sandboxes`` is an explicit int, ``effective_`` returns it."""
    settings = _settings(max_sandboxes=4)
    assert settings.effective_max_sandboxes() == 4


def test_effective_max_sandboxes_compute_from_cpu() -> None:
    """None mode computes cap from 70% usable CPU ÷ vcpus, min 8."""
    settings = _settings(vcpus=2, max_sandboxes=None)
    assert settings.effective_max_sandboxes(cpu_count=16) == 8
    assert settings.effective_max_sandboxes(cpu_count=32) == 11

    settings_4vcpu = _settings(vcpus=4, max_sandboxes=None)
    assert settings_4vcpu.effective_max_sandboxes(cpu_count=32) == 8


def test_effective_max_sandboxes_compute_min_floor() -> None:
    """Even a tiny host gets the minimum cap of 8."""
    settings = _settings(vcpus=2, max_sandboxes=None)
    assert settings.effective_max_sandboxes(cpu_count=1) == 8


def test_effective_max_sandboxes_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """``FLOWJET_SANDBOX_MAX`` env var overrides the YAML value."""
    settings = _settings(max_sandboxes=None)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "5")
    assert settings.effective_max_sandboxes(cpu_count=32) == 5


def test_effective_max_sandboxes_env_override_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """``FLOWJET_SANDBOX_MAX=0`` means unlimited via env override."""
    settings = _settings(max_sandboxes=4)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "0")
    assert settings.effective_max_sandboxes() == 0


def test_effective_max_sandboxes_env_override_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """``FLOWJET_SANDBOX_MAX=none`` defers to compute-sizing even if YAML pins a value."""
    settings = _settings(vcpus=2, max_sandboxes=4)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "none")
    assert settings.effective_max_sandboxes(cpu_count=32) == 11


def test_effective_max_sandboxes_env_override_falls_back_on_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unparseable env value falls back to the YAML field."""
    settings = _settings(max_sandboxes=3)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "garbage")
    assert settings.effective_max_sandboxes() == 3


def test_effective_max_sandboxes_env_percent_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``FLOWJET_SANDBOX_MAX_PERCENT`` tunes the CPU usable fraction (default 70)."""
    settings = _settings(vcpus=2, max_sandboxes=None)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "50")
    assert settings.effective_max_sandboxes(cpu_count=32) == 8
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "90")
    assert settings.effective_max_sandboxes(cpu_count=32) == 14


def test_effective_max_sandboxes_env_percent_invalid_uses_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An out-of-range percentage falls back to the 70% default."""
    settings = _settings(vcpus=2, max_sandboxes=None)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "150")
    assert settings.effective_max_sandboxes(cpu_count=32) == 11


def test_load_settings_requires_existing_explicit_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _ = SandboxSettingsLoader.load(tmp_path / "missing.yml")


def test_load_settings_from_explicit_path(tmp_path: Path) -> None:
    path = tmp_path / "nano.yml"
    _ = path.write_text(
        "models:\n  default: gpt-x\n"
        "sandbox:\n  enabled: true\n"
        "  backend:\n    type: arcbox\n"
        "    arcbox:\n      image: img:1\n      vcpus: 3\n",
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

    _ = default.write_text(
        "sandbox:\n  enabled: true\n  backend:\n    type: arcbox\n    arcbox:\n      image: img\n",
        encoding="utf-8",
    )
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
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1", vcpus=3, mem_mib=512))
    try:
        await manager.open_workspace(str(ws))
        backend = fake_backend.instances[0]
        assert backend._image == "img:1"
        assert backend._vcpus == 3
        assert backend._mem_mib == 512
        assert backend._network is False
        tree = backend.tree
        assert tree["/workspace/a.txt"] == b"alpha"
        assert tree["/workspace/sub/b.txt"] == b"beta"
        assert not any("__pycache__" in name for name in tree)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_reopen_without_changes_skips_push(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        await manager.close_workspace(str(ws))
        await manager.close_workspace(str(ws))  # unbalanced close: no-op
        backend = fake_backend.instances[0]
        backend.uploaded_files.clear()

        await manager.open_workspace(str(ws))  # manifest matches: no push
        assert backend.uploaded_files == []
        await manager.close_workspace(str(ws))

        # Host-side change between sessions: the next open pushes exactly the changed file.
        _ = (ws / "a.txt").write_text("alpha-2")
        await manager.open_workspace(str(ws))
        assert backend.uploaded_files == ["/workspace/a.txt"]
        assert backend.tree["/workspace/a.txt"] == b"alpha-2"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_second_concurrent_open_skips_push(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        backend = fake_backend.instances[0]
        backend.uploaded_files.clear()
        _ = (ws / "a.txt").write_text("peer-active")

        # A peer session is mid-run: the push must not clobber live guest state.
        await manager.open_workspace(str(ws))
        assert backend.uploaded_files == []
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_close_pulls_guest_changes_back_to_host(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        backend = fake_backend.instances[0]
        # Agent wrote a new file and modified an existing one in the guest.
        backend.tree["/workspace/out/report.md"] = b"# done"
        backend.tree["/workspace/a.txt"] = b"alpha-2"

        await manager.close_workspace(str(ws))
        assert (ws / "out" / "report.md").read_bytes() == b"# done"
        assert (ws / "a.txt").read_text() == "alpha-2"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_close_propagates_guest_deletions_to_host(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    """A file the agent deleted inside the guest is removed from the host."""
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        backend = fake_backend.instances[0]
        _ = backend.tree.pop("/workspace/sub/b.txt")

        await manager.close_workspace(str(ws))
        assert not (ws / "sub" / "b.txt").exists()
        assert not (ws / "sub").exists()  # emptied parent pruned
        assert (ws / "a.txt").read_text() == "alpha"  # untouched file survives
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_pull_never_deletes_host_files_added_after_push(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    """Host files created after the push are not in the manifest — never deleted."""
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        backend = fake_backend.instances[0]
        _ = backend.tree.pop("/workspace/a.txt")
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
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1"))
    try:
        await manager.open_workspace(str(ws))
        await manager.open_workspace(str(ws))  # second active run
        backend = fake_backend.instances[0]
        backend.tree["/workspace/new.txt"] = b"new"

        await manager.close_workspace(str(ws))  # one run still active
        assert not (ws / "new.txt").exists()

        await manager.close_workspace(str(ws))  # last run: pull
        assert (ws / "new.txt").read_bytes() == b"new"
    finally:
        await manager.shutdown()


@pytest.mark.usefixtures("fake_backend")
@pytest.mark.asyncio
async def test_backend_for_binds_and_caches(tmp_path: Path) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(
        _settings(image="img:1", workspace_root="/data", default_timeout=42)
    )
    try:
        with pytest.raises(RuntimeError):
            manager.backend_for(str(ws))  # not opened yet

        await manager.open_workspace(str(ws))
        backend = manager.backend_for(str(ws))
        assert backend.workspace_root == "/data"
        assert backend.default_timeout == 42
        assert manager.backend_for(str(ws)) is backend  # cached per lease
        assert manager.guest_workspace == "/data"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_max_sandboxes_evicts_idle_lru(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    manager = ToolSandboxManager(_settings(image="img:1", max_sandboxes=1))
    try:
        await manager.open_workspace(str(ws1))
        backend1 = fake_backend.instances[0]
        await manager.close_workspace(str(ws1))
        await manager.open_workspace(str(ws2))
        assert backend1.closed  # evicted (idle, LRU)
        assert manager.lease_count == 1
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_max_sandboxes_zero_means_unlimited(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    """``max_sandboxes: 0`` disables LRU eviction — all idle sandboxes stay."""
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    manager = ToolSandboxManager(_settings(image="img:1", max_sandboxes=0))
    try:
        await manager.open_workspace(str(ws1))
        backend1 = fake_backend.instances[0]
        await manager.close_workspace(str(ws1))
        await manager.open_workspace(str(ws2))
        assert not backend1.closed  # NOT evicted — unlimited
        assert manager.lease_count == 2
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_idle_reaper_kills_stale_sandboxes(
    fake_backend: type[FakeArcBoxBackend],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import flowjet.core.sandbox.arbox as arbox_mod

    monkeypatch.setattr(arbox_mod, "_REAPER_INTERVAL_SECONDS", 0.05)
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1", idle_timeout_seconds=0.01))
    await manager.open_workspace(str(ws))
    backend = fake_backend.instances[0]
    await manager.close_workspace(str(ws))
    await asyncio.sleep(0.3)
    assert backend.closed
    assert manager.lease_count == 0
    await manager.shutdown()


@pytest.mark.asyncio
async def test_shutdown_kills_all_and_closes_backend(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1"))
    await manager.open_workspace(str(ws))
    backend = fake_backend.instances[0]
    await manager.shutdown()
    assert backend.closed

    await manager.shutdown()  # idempotent


# ---------------------------------------------------------------------------
# Disk watermark guard (SandboxDiskFullError)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_refuses_below_disk_watermark(
    fake_backend: type[FakeArcBoxBackend],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1", min_free_bytes=1024))
    try:
        # Patch the factory to set a low free space on the created backend.
        def _low_free_create(config):
            arcbox = getattr(config, "arcbox", None)
            kwargs = {}
            for field in (
                "image",
                "vcpus",
                "mem_mib",
                "network",
                "workspace_root",
                "default_timeout",
                "connect_timeout",
                "idle_timeout_seconds",
                "min_free_bytes",
                "api_url",
                "api_key",
            ):
                val = getattr(arcbox, field, None)
                if val is not None:
                    kwargs[field] = val
            backend = FakeArcBoxBackend(**kwargs)
            backend._free_space = 512  # below the 1024-byte watermark
            return backend

        import soothe_nano.sandbox as sandbox_mod

        monkeypatch.setattr(sandbox_mod, "create_sandbox_backend", _low_free_create)
        try:
            with pytest.raises(SandboxDiskFullError, match="guest disk full"):
                await manager.open_workspace(str(ws))
            lease = manager._leases[str(ws)]
            assert lease.active_runs == 0
        finally:
            monkeypatch.undo()
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_open_passes_above_disk_watermark(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1", min_free_bytes=1024))
    try:
        await manager.open_workspace(str(ws))
        assert manager._leases[str(ws)].active_runs == 1
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_open_skips_probe_when_watermark_disabled(
    fake_backend: type[FakeArcBoxBackend], tmp_path: Path
) -> None:
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_settings(image="img:1"))
    try:
        await manager.open_workspace(str(ws))
    finally:
        await manager.shutdown()


def test_probe_uses_backend_free_space_bytes() -> None:
    """The probe prefers the backend's ``free_space_bytes`` helper."""

    class HelperBackend:
        def free_space_bytes(self, path: str | None = None) -> int | None:
            return 8192

    assert ToolSandboxManager._probe_free_bytes(HelperBackend()) == 8192


def test_probe_fails_open_when_backend_raises() -> None:
    class BrokenBackend:
        def free_space_bytes(self, path: str | None = None) -> int | None:
            raise RuntimeError("transport gone")

    assert ToolSandboxManager._probe_free_bytes(BrokenBackend()) is None


def test_probe_returns_none_when_no_helper() -> None:
    class NoHelperBackend:
        pass

    assert ToolSandboxManager._probe_free_bytes(NoHelperBackend()) is None


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
    manager = cast(ToolSandboxManager, cast(object, fake_manager))
    resolver = SandboxAwareWorkspaceResolver(inner, manager)

    assert resolver.resolve("s") == Path("/tmp/rec-ws")

    await resolver.open_session("s", Path("/tmp/rec-ws"))
    await resolver.close_session("s", Path("/tmp/rec-ws"))
    await resolver.shutdown()
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
        cast(ToolSandboxManager, cast(object, RecordingManager())),
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
            self.sandbox_ids: dict[str, str] = {str(tmp_path): "sbx-live"}

        def backend_for(self, workspace: str) -> object:
            return self.backends[workspace]

        def sandbox_id_for(self, workspace: str) -> str | None:
            return self.sandbox_ids.get(workspace)

    fake_manager = FakeManager()
    manager = cast(ToolSandboxManager, cast(object, fake_manager))
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

    # Same workspace, same live sandbox: the built agent is reused.
    events = [event async for event in adapter.astream(req)]
    assert len(events) >= 1
    assert len(built) == 1

    # The workspace's sandbox was replaced: the cached graph must rebuild.
    fake_manager.sandbox_ids[str(tmp_path)] = "sbx-2"
    events = [event async for event in adapter.astream(req)]
    assert len(events) >= 1
    assert len(built) == 2

    # A different workspace rebuilds too.
    req2 = IsolatedRunRequest(
        run_id="r2",
        session="s2",
        input_text="hi",
        model="default",
        workspace=tmp_path / "other",
    )
    fake_manager.backends[str(tmp_path / "other")] = object()
    fake_manager.sandbox_ids[str(tmp_path / "other")] = "sbx-other"
    events = [event async for event in adapter.astream(req2)]
    assert len(events) >= 1
    assert len(built) == 3
    assert adapter.generation == 3


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


@pytest.mark.usefixtures("fake_backend")
def test_build_sandbox_manager_enabled(tmp_path: Path) -> None:
    from flowjet.server.http.app import build_sandbox_manager, build_workspace_resolver

    settings = _settings_for(
        tmp_path,
        "sandbox:\n  enabled: true\n"
        "  backend:\n    type: arcbox\n"
        "    arcbox:\n      image: flowjet-server:latest\n",
    )
    manager = build_sandbox_manager(settings)
    assert manager is not None
    assert manager.settings.image == "flowjet-server:latest"

    # Without workspace sync the local resolver is wrapped for staging.
    resolver = build_workspace_resolver(settings, manager)
    assert isinstance(resolver, SandboxAwareWorkspaceResolver)

    # Sandbox config missing an image fails loud at startup.
    bad = _settings_for(
        tmp_path,
        "sandbox:\n  enabled: true\n  backend:\n    type: arcbox\n    arcbox: {}\n",
    )
    with pytest.raises(ValueError, match="image"):
        _ = build_sandbox_manager(bad)
