"""Tool sandbox — nano.yml parsing, manager lifecycle, staging, adapter binding.

Tests mock soothe-nano's sandbox backend factory (``create_sandbox_backend``)
instead of any specific backend SDK: flowjet is backend-agnostic and delegates
construction to nano's factory. The factory is patched to return a fake whose
``execute`` / ``upload_files`` / ``download_files`` / ``free_space_bytes`` /
``id`` / ``close`` shape mirrors the real contract.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import cast

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
    min_free_bytes: int = 0,
    api_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Build a ``sandbox.backend`` dict in the multi-backend config format.

    ``idle_timeout_seconds`` is intentionally NOT placed in the backend
    sub-config: it is a pool-management field owned by flowjet's settings
    layer (the idle reaper). nano's ``ArcBoxBackendConfig`` enforces
    ``idle_timeout_seconds >= 1`` on its own copy, so forwarding a small
    reaper timeout here would make the backend reject the config at spawn
    time. The backend keeps its default (300s) for its own guest reaper.
    """
    arcbox: dict = {"image": image, "vcpus": vcpus, "mem_mib": mem_mib}
    if network:
        arcbox["network"] = True
    if workspace_root != "/workspace":
        arcbox["workspace_root"] = workspace_root
    if default_timeout != 120:
        arcbox["default_timeout"] = default_timeout
    if connect_timeout != 60.0:
        arcbox["connect_timeout"] = connect_timeout
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
    """Build ToolSandboxSettings with the new backend config format.

    ``idle_timeout_seconds`` is set at the top level (pool reaper) only; the
    backend config field is left to its default so soothe_nano's ``>= 1``
    validation does not reject small reaper timeouts used in tests.
    """
    backend = _backend_cfg(
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
        lambda: _settings(max_sandboxes=-1),  # negative cap
    ],
)
def test_parse_rejects_invalid_settings(factory: Callable[[], ToolSandboxSettings]) -> None:
    """Pool-management fields owned by flowjet are validated at parse time.

    Backend-specific fields (``image``, ``vcpus``, ``mem_mib``) are opaque to
    flowjet and deferred to nano's :func:`create_sandbox_backend` at spawn
    time — see :func:`test_build_sandbox_manager_enabled`, which accepts a
    bare ``arcbox: {}`` config with no image. ``min_free_bytes`` rejection is
    covered by :func:`test_disk_watermark_negative_rejected`.
    """
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
async def test_backend_for_binds_and_caches(tmp_path: Path, make_workspace) -> None:
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_workspace,
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
            backend = fake_backend(**kwargs)
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
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
        def __init__(self) -> None:
            self.backends: dict[str, object] = {str(tmp_path): object()}
            self.sandbox_ids: dict[str, str] = {str(tmp_path): "sbx-live"}

        def backend_for(self, workspace: str) -> object:
            return self.backends[workspace]

        def sandbox_id_for(self, workspace: str) -> str | None:
            return self.sandbox_ids.get(workspace)

        def guest_workspace_for(self, workspace: str) -> str:
            return "/workspace"

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


def test_build_sandbox_manager_disabled_when_mode_off(tmp_path: Path) -> None:
    """``sandbox_mode=off`` disables the sandbox even with no config section."""
    from flowjet.server.http.app import build_sandbox_manager

    settings = _settings_for(tmp_path, "models:\n  default: gpt-x\n")
    settings = settings.model_copy(update={"sandbox_mode": "off"})
    assert build_sandbox_manager(settings) is None


@pytest.mark.usefixtures("fake_backend")
def test_build_sandbox_manager_auto_enables_os_sandbox(tmp_path: Path) -> None:
    """``sandbox_mode=auto`` (production default) enables os_sandbox with no config section."""
    from flowjet.server.http.app import build_sandbox_manager

    settings = _settings_for(tmp_path, "models:\n  default: gpt-x\n")
    # sandbox_mode defaults to "auto"
    manager = build_sandbox_manager(settings)
    assert manager is not None
    assert manager.settings.is_os_sandbox is True
    assert manager.settings.enabled is True


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

    # An empty arcbox config is accepted by flowjet (image validation is
    # deferred to nano's factory at spawn time, not flowjet's settings layer).
    bare = _settings_for(
        tmp_path,
        "sandbox:\n  enabled: true\n  backend:\n    type: arcbox\n    arcbox: {}\n",
    )
    bare_manager = build_sandbox_manager(bare)
    assert bare_manager is not None
    assert bare_manager.settings.image is None


# ---------------------------------------------------------------------------
# os_sandbox backend: identity path mapping (no push/pull staging)
# ---------------------------------------------------------------------------


def _os_sandbox_settings(
    *,
    enabled: bool = True,
    max_sandboxes: int | None = 8,
    idle_timeout_seconds: float = 300.0,
    linux_tier: str = "auto",
    allow_degraded: bool = False,
    default_timeout: int = 120,
) -> ToolSandboxSettings:
    """Build ToolSandboxSettings with an os_sandbox backend config."""
    return ToolSandboxSettings(
        enabled=enabled,
        backend={
            "type": "os_sandbox",
            "os_sandbox": {
                "workspace_root": None,
                "linux_tier": linux_tier,
                "allow_degraded": allow_degraded,
                "default_timeout": default_timeout,
            },
        },
        max_sandboxes=max_sandboxes,
        idle_timeout_seconds=idle_timeout_seconds,
        min_free_bytes=0,
    )


def test_os_sandbox_is_os_sandbox_flag() -> None:
    """The ``is_os_sandbox`` flag is True for os_sandbox backends."""
    settings = _os_sandbox_settings()
    assert settings.is_os_sandbox is True
    assert settings.backend_type == "os_sandbox"

    # arcbox backends are not os_sandbox
    arcbox_settings = _settings(image="img:1")
    assert arcbox_settings.is_os_sandbox is False


def test_os_sandbox_default_os_sandbox_factory() -> None:
    """``ToolSandboxSettings.default_os_sandbox()`` builds production defaults."""
    settings = ToolSandboxSettings.default_os_sandbox()
    assert settings.enabled is True
    assert settings.is_os_sandbox is True
    assert settings.backend_type == "os_sandbox"
    assert settings.max_sandboxes == 8


def test_parse_os_sandbox_section() -> None:
    """The loader parses os_sandbox backend config from nano.yml."""
    settings = SandboxSettingsLoader.parse_section(
        {
            "enabled": True,
            "backend": {
                "type": "os_sandbox",
                "os_sandbox": {
                    "workspace_root": None,
                    "linux_tier": "bwrap",
                    "allow_degraded": False,
                    "default_timeout": 60,
                },
            },
            "max_sandboxes": 4,
        }
    )
    assert settings.enabled is True
    assert settings.is_os_sandbox is True
    assert settings.default_timeout == 60
    assert settings.max_sandboxes == 4


@pytest.mark.asyncio
async def test_os_sandbox_open_binds_workspace_no_staging(
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
) -> None:
    """os_sandbox binds the workspace at spawn; no push/pull staging occurs."""
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        await manager.open_workspace(str(ws))
        backend = fake_backend.instances[0]
        # bind_workspace was called with the host workspace path
        assert backend._bound_workspace == str(ws)
        # No files were uploaded (identity mapping — no staging)
        assert backend.uploaded_files == []
        assert backend.tree == {}
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_os_sandbox_close_skips_pull(
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
) -> None:
    """os_sandbox close is a no-op for file transfer (identity mapping)."""
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        await manager.open_workspace(str(ws))
        backend = fake_backend.instances[0]
        # Simulate a guest write — for os_sandbox this is already on the host.
        # The tree should stay empty (no staging).
        await manager.close_workspace(str(ws))
        # No find command was issued (no pull listing)
        assert not any(cmd.startswith("find") for cmd in backend.executed_commands)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_os_sandbox_guest_workspace_for_returns_host_path(
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
) -> None:
    """``guest_workspace_for`` returns the host path for os_sandbox (identity)."""
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        await manager.open_workspace(str(ws))
        # os_sandbox: guest workspace == host workspace (identity mapping)
        assert manager.guest_workspace_for(str(ws)) == str(ws)
        # arcbox would return the configured guest root
        arcbox_manager = ToolSandboxManager(_settings(image="img:1", workspace_root="/data"))
        await arcbox_manager.open_workspace(str(ws))
        assert arcbox_manager.guest_workspace_for(str(ws)) == "/data"
        await arcbox_manager.shutdown()
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_os_sandbox_reopen_reuses_bound_workspace(
    fake_backend: type,
    tmp_path: Path,
    make_workspace,
) -> None:
    """Reopening an os_sandbox workspace reuses the same bound backend."""
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        await manager.open_workspace(str(ws))
        backend1 = fake_backend.instances[0]
        await manager.close_workspace(str(ws))
        await manager.open_workspace(str(ws))
        # Same backend reused (lease cached)
        assert fake_backend.instances[-1] is backend1
        assert backend1._bound_workspace == str(ws)
    finally:
        await manager.shutdown()
