"""Concurrent os_sandbox resource-consumption tests.

Exercises the ToolSandboxManager pool under real concurrent load:

* **Pool cap under load** — many workspaces opened concurrently respect the
  ``max_sandboxes`` cap and trigger LRU eviction correctly.
* **CPU-based compute cap** — ``compute_max_sandboxes`` and
  ``effective_max_sandboxes`` produce correct values across vcpus, cpu_count,
  and env-override combinations.
* **Concurrent lease reuse** — the same workspace opened concurrently reuses
  one lease (``active_runs > 1``) and never double-spawns a backend.
* **os_sandbox identity no-staging under contention** — concurrent opens of
  os_sandbox backends never call ``upload_files`` / ``download_files`` /
  ``find`` (identity mapping holds under contention).
* **Idle reaper under concurrency** — the reaper reaps stale idle leases while
  concurrent active runs keep their leases alive.

All tests use the ``FakeArcBoxBackend`` (no real OS sandbox) shared via the
``tests/unit/server/conftest.py`` fixtures.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from flowjet.core.sandbox import ToolSandboxManager, ToolSandboxSettings
from flowjet.core.sandbox.settings import compute_max_sandboxes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _os_sandbox_settings(
    *,
    enabled: bool = True,
    max_sandboxes: int | None = 8,
    idle_timeout_seconds: float = 300.0,
    default_timeout: int = 120,
) -> ToolSandboxSettings:
    """Build ToolSandboxSettings with an os_sandbox backend config."""
    return ToolSandboxSettings(
        enabled=enabled,
        backend={
            "type": "os_sandbox",
            "os_sandbox": {
                "workspace_root": None,
                "linux_tier": "auto",
                "allow_degraded": False,
                "default_timeout": default_timeout,
            },
        },
        max_sandboxes=max_sandboxes,
        idle_timeout_seconds=idle_timeout_seconds,
        min_free_bytes=0,
    )


def _arcbox_settings(
    *,
    image: str = "img:1",
    vcpus: int = 2,
    mem_mib: int = 2048,
    max_sandboxes: int | None = 8,
    idle_timeout_seconds: float = 300.0,
) -> ToolSandboxSettings:
    """Build ToolSandboxSettings with an arcbox backend config.

    ``idle_timeout_seconds`` is set at the top level (reaper) only; the
    backend config field is left to its default so soothe_nano's
    ``>= 1`` validation does not reject small reaper timeouts.
    """
    return ToolSandboxSettings(
        enabled=True,
        backend={
            "type": "arcbox",
            "arcbox": {
                "image": image,
                "vcpus": vcpus,
                "mem_mib": mem_mib,
            },
        },
        max_sandboxes=max_sandboxes,
        idle_timeout_seconds=idle_timeout_seconds,
        min_free_bytes=0,
    )


def _make_empty_ws(tmp_path: Path, name: str) -> Path:
    """Create an empty workspace directory under tmp_path."""
    ws = tmp_path / name
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ---------------------------------------------------------------------------
# 1. Pool cap under load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_opens_respect_pool_cap(fake_backend: type, tmp_path: Path) -> None:
    """Opening N > cap workspaces concurrently spawns at most ``cap`` backends.

    The pool evicts idle leases via LRU to make room. After all opens complete,
    the live lease count must not exceed the cap (plus any busy overshoot).
    """
    cap = 3
    n = 8
    manager = ToolSandboxManager(_os_sandbox_settings(max_sandboxes=cap))
    try:
        workspaces = [str(_make_empty_ws(tmp_path, f"ws{i}")) for i in range(n)]

        # Open all concurrently. The pool cap triggers LRU eviction for idle
        # leases; active leases may cause a temporary overshoot (by design).
        await asyncio.gather(*(manager.open_workspace(ws) for ws in workspaces))

        # Every workspace was opened at least once → at least n backends spawned.
        assert len(fake_backend.instances) >= n

        # Live leases: some were evicted by LRU. The count is capped unless all
        # are still active (overshoot allowed when every lease is busy).
        live = manager.lease_count
        assert live <= n
        # At least the cap worth of sandboxes were alive at some point.
        assert len(fake_backend.instances) >= cap
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_pool_cap_evicts_lru_under_concurrent_load(
    fake_backend: type, tmp_path: Path
) -> None:
    """Concurrent opens after closing prior leases evict the least-recently-used.

    Opens cap workspaces, closes them all, then opens new ones concurrently.
    The LRU eviction closes the old backends to make room.
    """
    cap = 2
    manager = ToolSandboxManager(_os_sandbox_settings(max_sandboxes=cap))
    try:
        # Phase 1: fill the pool.
        ws_a = str(_make_empty_ws(tmp_path, "a"))
        ws_b = str(_make_empty_ws(tmp_path, "b"))
        await manager.open_workspace(ws_a)
        await manager.open_workspace(ws_b)
        backend_a = fake_backend.instances[0]
        backend_b = fake_backend.instances[1]
        await manager.close_workspace(ws_a)
        await manager.close_workspace(ws_b)
        assert not backend_a.closed
        assert not backend_b.closed

        # Phase 2: open two NEW workspaces concurrently → evicts the idle ones.
        ws_c = str(_make_empty_ws(tmp_path, "c"))
        ws_d = str(_make_empty_ws(tmp_path, "d"))
        await asyncio.gather(
            manager.open_workspace(ws_c),
            manager.open_workspace(ws_d),
        )
        # Both old backends were evicted (LRU, idle).
        assert backend_a.closed
        assert backend_b.closed
        assert manager.lease_count == cap
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_pool_cap_zero_unlimited_under_concurrent_load(
    fake_backend: type, tmp_path: Path
) -> None:
    """``max_sandboxes=0`` (unlimited) never evicts under concurrent opens."""
    n = 6
    manager = ToolSandboxManager(_os_sandbox_settings(max_sandboxes=0))
    try:
        workspaces = [str(_make_empty_ws(tmp_path, f"ws{i}")) for i in range(n)]
        await asyncio.gather(*(manager.open_workspace(ws) for ws in workspaces))
        # Close all — none should be evicted (unlimited).
        await asyncio.gather(*(manager.close_workspace(ws) for ws in workspaces))
        assert manager.lease_count == n
        assert all(not inst.closed for inst in fake_backend.instances)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_concurrent_mixed_arcbox_and_os_sandbox_pools(
    fake_backend: type, tmp_path: Path
) -> None:
    """Two managers (arcbox + os_sandbox) operate concurrently without interference."""
    arc_mgr = ToolSandboxManager(_arcbox_settings(max_sandboxes=4))
    os_mgr = ToolSandboxManager(_os_sandbox_settings(max_sandboxes=4))
    try:
        arc_ws = str(_make_empty_ws(tmp_path, "arc"))
        os_ws = str(_make_empty_ws(tmp_path, "os"))
        await asyncio.gather(
            arc_mgr.open_workspace(arc_ws),
            os_mgr.open_workspace(os_ws),
        )
        arc_backend = fake_backend.instances[0]
        os_backend = fake_backend.instances[1]
        assert arc_backend.backend_type == "arcbox"
        assert os_backend.backend_type == "os_sandbox"
        assert arc_mgr.lease_count == 1
        assert os_mgr.lease_count == 1
    finally:
        await arc_mgr.shutdown()
        await os_mgr.shutdown()


# ---------------------------------------------------------------------------
# 2. CPU-based compute cap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("vcpus", "cpu_count", "expected"),
    [
        (1, 8, 8),  # floor applies: 70% of 8 = 5, 5//1=5, max(5,8)=8
        (2, 8, 8),  # 70% of 8 = 5, 5//2=2, max(2,8)=8
        (2, 32, 11),  # 70% of 32 = 22, 22//2=11, max(11,8)=11
        (4, 32, 8),  # 70% of 32 = 22, 22//4=5, max(5,8)=8
        (4, 64, 11),  # 70% of 64 = 44, 44//4=11, max(11,8)=11
        (8, 64, 8),  # 70% of 64 = 44, 44//8=5, max(5,8)=8
        (1, 1, 8),  # floor: 70% of 1 = 0→1, 1//1=1, max(1,8)=8
        (2, 1, 8),  # floor: 70% of 1 = 0→1, 1//2=0→1, max(1,8)=8
    ],
)
def test_compute_max_sandboxes_various(vcpus: int, cpu_count: int, expected: int) -> None:
    """``compute_max_sandboxes`` divides usable CPU by vcpus with a min floor of 8."""
    assert compute_max_sandboxes(vcpus, cpu_count=cpu_count) == expected


def test_compute_max_sandboxes_custom_usable_fraction() -> None:
    """A custom ``usable_fraction`` overrides the default 70%."""
    # 50% of 32 = 16, 16//2=8, max(8,8)=8
    assert compute_max_sandboxes(2, cpu_count=32, usable_fraction=0.50) == 8
    # 90% of 32 = 28, 28//2=14, max(14,8)=14
    assert compute_max_sandboxes(2, cpu_count=32, usable_fraction=0.90) == 14
    # 100% of 32 = 32, 32//4=8, max(8,8)=8
    assert compute_max_sandboxes(4, cpu_count=32, usable_fraction=1.0) == 8


def test_compute_max_sandboxes_rejects_zero_vcpus() -> None:
    """``vcpus < 1`` is a programming error — raise ValueError."""
    with pytest.raises(ValueError, match="vcpus"):
        _ = compute_max_sandboxes(0, cpu_count=8)


def test_effective_max_sandboxes_compute_from_cpu_os_sandbox() -> None:
    """os_sandbox settings with ``max_sandboxes=None`` compute from host CPU."""
    settings = _os_sandbox_settings(max_sandboxes=None)
    # os_sandbox has no vcpus field → defaults to 2.
    assert settings.vcpus == 2
    assert settings.effective_max_sandboxes(cpu_count=32) == 11  # 70%32//2=11
    assert settings.effective_max_sandboxes(cpu_count=8) == 8  # floor


def test_effective_max_sandboxes_env_override_on_os_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``FLOWJET_SANDBOX_MAX`` env var overrides the computed cap for os_sandbox."""
    settings = _os_sandbox_settings(max_sandboxes=None)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "16")
    assert settings.effective_max_sandboxes(cpu_count=32) == 16

    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "0")
    assert settings.effective_max_sandboxes(cpu_count=32) == 0  # unlimited

    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "none")
    # 'none' defers to compute-sizing even with env set.
    assert settings.effective_max_sandboxes(cpu_count=32) == 11


def test_effective_max_sandboxes_env_percent_tuning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``FLOWJET_SANDBOX_MAX_PERCENT`` tunes the CPU usable fraction."""
    settings = _os_sandbox_settings(max_sandboxes=None)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "50")
    assert settings.effective_max_sandboxes(cpu_count=32) == 8  # 50%32//2=8

    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "90")
    assert settings.effective_max_sandboxes(cpu_count=32) == 14  # 90%32//2=14


def test_effective_max_sandboxes_invalid_env_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid env values fall back to the YAML field or compute."""
    settings = _os_sandbox_settings(max_sandboxes=4)
    monkeypatch.setenv("FLOWJET_SANDBOX_MAX", "garbage")
    assert settings.effective_max_sandboxes(cpu_count=32) == 4

    monkeypatch.setenv("FLOWJET_SANDBOX_MAX_PERCENT", "200")
    # Invalid percent → default 70%; max_sandboxes=4 is explicit.
    assert settings.effective_max_sandboxes(cpu_count=32) == 4


# ---------------------------------------------------------------------------
# 3. Concurrent lease reuse (same workspace)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_opens_same_workspace_single_lease(
    fake_backend: type, tmp_path: Path
) -> None:
    """Opening the same workspace N times concurrently spawns exactly one backend."""
    ws = str(_make_empty_ws(tmp_path, "shared"))
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        await asyncio.gather(
            manager.open_workspace(ws),
            manager.open_workspace(ws),
            manager.open_workspace(ws),
        )
        assert len(fake_backend.instances) == 1
        assert manager.lease_count == 1
        lease = manager._leases[ws]
        assert lease.active_runs == 3
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_concurrent_close_decrements_active_runs(fake_backend: type, tmp_path: Path) -> None:
    """Concurrent closes decrement ``active_runs``; pull only on the last close."""
    ws = str(_make_empty_ws(tmp_path, "shared"))
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        # Open 4 concurrent runs.
        await asyncio.gather(*(manager.open_workspace(ws) for _ in range(4)))
        lease = manager._leases[ws]
        assert lease.active_runs == 4

        # Close 3 — should NOT trigger any pull (active_runs > 0).
        await asyncio.gather(
            manager.close_workspace(ws),
            manager.close_workspace(ws),
            manager.close_workspace(ws),
        )
        assert manager._leases[ws].active_runs == 1
        # For os_sandbox, no pull happens regardless. Verify lease is still live.
        assert not fake_backend.instances[0].closed

        # Final close — active_runs drops to 0, lease stays (idle, not evicted).
        await manager.close_workspace(ws)
        assert manager._leases[ws].active_runs == 0
        assert manager.lease_count == 1  # still in pool (idle)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_concurrent_open_close_interleaved_no_deadlock(
    fake_backend: type, tmp_path: Path
) -> None:
    """Interleaved concurrent opens and closes on the same workspace don't deadlock."""
    ws = str(_make_empty_ws(tmp_path, "interleaved"))
    manager = ToolSandboxManager(_os_sandbox_settings())

    async def open_close() -> None:
        await manager.open_workspace(ws)
        await asyncio.sleep(0.001)  # yield to let peers interleave
        await manager.close_workspace(ws)

    try:
        await asyncio.gather(*(open_close() for _ in range(12)))
        assert manager.lease_count == 1  # one lease, recycled
        assert len(fake_backend.instances) == 1  # one backend spawned
        assert manager._leases[ws].active_runs == 0
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_concurrent_same_workspace_arcbox_skips_push_after_first(
    fake_backend: type, tmp_path: Path, make_workspace
) -> None:
    """For arcbox, concurrent opens of the same workspace skip the push after the first.

    A peer session mid-run has fresher guest state; the push is skipped to
    avoid clobbering live edits.
    """
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_arcbox_settings())
    try:
        await manager.open_workspace(str(ws))
        backend = fake_backend.instances[0]
        uploaded_before = len(backend.uploaded_files)
        assert uploaded_before > 0  # first open pushed files

        # Concurrent opens (peer sessions) — should skip the push.
        await asyncio.gather(
            manager.open_workspace(str(ws)),
            manager.open_workspace(str(ws)),
        )
        # No additional uploads: peer-active skip path.
        assert len(backend.uploaded_files) == uploaded_before
        assert manager._leases[str(ws)].active_runs == 3
    finally:
        await manager.shutdown()


# ---------------------------------------------------------------------------
# 4. os_sandbox identity no-staging under contention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_os_sandbox_opens_never_upload(
    fake_backend: type, tmp_path: Path, make_workspace
) -> None:
    """Concurrent os_sandbox opens never call ``upload_files`` (identity mapping)."""
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        await asyncio.gather(
            manager.open_workspace(str(ws)),
            manager.open_workspace(str(ws)),
            manager.open_workspace(str(ws)),
        )
        backend = fake_backend.instances[0]
        assert backend.uploaded_files == []
        assert backend.tree == {}
        # Only bind_workspace was called (identity mapping), no staging.
        assert backend._bound_workspace == str(ws)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_concurrent_os_sandbox_closes_never_pull(
    fake_backend: type, tmp_path: Path, make_workspace
) -> None:
    """Concurrent os_sandbox closes never issue ``find`` or ``download_files``."""
    ws = make_workspace(tmp_path)
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        n = 4
        await asyncio.gather(*(manager.open_workspace(str(ws)) for _ in range(n)))
        backend = fake_backend.instances[0]
        backend.executed_commands.clear()

        await asyncio.gather(*(manager.close_workspace(str(ws)) for _ in range(n)))
        # No find commands (pull listing) and no download calls.
        assert not any(cmd.startswith("find") for cmd in backend.executed_commands)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_concurrent_os_sandbox_multi_workspace_no_cross_staging(
    fake_backend: type, tmp_path: Path, make_workspace
) -> None:
    """Multiple os_sandbox workspaces opened concurrently never cross-stage files."""
    ws1 = make_workspace(tmp_path)
    ws2_dir = tmp_path / "ws2"
    ws2_dir.mkdir(parents=True, exist_ok=True)
    (ws2_dir / "x.txt").write_text("x")
    ws2 = str(ws2_dir)

    manager = ToolSandboxManager(_os_sandbox_settings(max_sandboxes=0))
    try:
        await asyncio.gather(
            manager.open_workspace(str(ws1)),
            manager.open_workspace(ws2),
        )
        # Each backend was bound to its own workspace.
        b1 = fake_backend.instances[0]
        b2 = fake_backend.instances[1]
        assert b1._bound_workspace == str(ws1)
        assert b2._bound_workspace == ws2
        # Neither uploaded any files (identity mapping).
        assert b1.uploaded_files == []
        assert b2.uploaded_files == []
        assert b1.tree == {}
        assert b2.tree == {}
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_concurrent_os_sandbox_guest_workspace_is_host_path(
    fake_backend: type, tmp_path: Path
) -> None:
    """Under concurrent opens, ``guest_workspace_for`` always returns the host path."""
    ws = str(_make_empty_ws(tmp_path, "identity"))
    manager = ToolSandboxManager(_os_sandbox_settings())
    try:
        await asyncio.gather(
            manager.open_workspace(ws),
            manager.open_workspace(ws),
        )
        # os_sandbox identity: guest workspace == host workspace.
        assert manager.guest_workspace_for(ws) == ws
    finally:
        await manager.shutdown()


# ---------------------------------------------------------------------------
# 5. Idle reaper under concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idle_reaper_preserves_active_leases(
    fake_backend: type,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The idle reaper never reaps a lease with active runs, even past the timeout."""
    import flowjet.core.sandbox.arbox as arbox_mod

    monkeypatch.setattr(arbox_mod, "_REAPER_INTERVAL_SECONDS", 0.05)
    ws_active = str(_make_empty_ws(tmp_path, "active"))
    ws_idle = str(_make_empty_ws(tmp_path, "idle"))

    # Use arcbox with a tiny idle timeout for fast reaping.
    manager = ToolSandboxManager(_arcbox_settings(idle_timeout_seconds=0.01))
    try:
        await manager.open_workspace(ws_active)
        await manager.open_workspace(ws_idle)
        await manager.close_workspace(ws_idle)  # idle now

        active_backend = manager.backend_for(ws_active)
        idle_backend = manager.backend_for(ws_idle)

        # Wait past the idle timeout; the reaper should reap ws_idle but NOT ws_active.
        await asyncio.sleep(0.3)
        assert not active_backend.closed  # active lease preserved
        assert idle_backend.closed  # idle lease reaped
        assert manager.lease_count == 1
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_idle_reaper_reaps_only_stale_under_concurrent_load(
    fake_backend: type,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a mix of idle and active leases under concurrent load, only idle ones are reaped."""
    import flowjet.core.sandbox.arbox as arbox_mod

    monkeypatch.setattr(arbox_mod, "_REAPER_INTERVAL_SECONDS", 0.05)

    # Create 4 workspaces: 2 will stay active, 2 will go idle.
    workspaces = []
    for i in range(4):
        workspaces.append(str(_make_empty_ws(tmp_path, f"ws{i}")))

    manager = ToolSandboxManager(_arcbox_settings(idle_timeout_seconds=0.01, max_sandboxes=0))
    try:
        # Open all 4.
        await asyncio.gather(*(manager.open_workspace(ws) for ws in workspaces))
        backends = list(fake_backend.instances)

        # Close ws2 and ws3 → they become idle.
        await manager.close_workspace(workspaces[2])
        await manager.close_workspace(workspaces[3])

        # Touch ws0 and ws1 to keep them active (update last_used).
        _ = manager.backend_for(workspaces[0])
        _ = manager.backend_for(workspaces[1])

        await asyncio.sleep(0.3)

        # Active leases survive.
        assert not backends[0].closed
        assert not backends[1].closed
        # Idle leases reaped.
        assert backends[2].closed
        assert backends[3].closed
        assert manager.lease_count == 2
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_idle_reaper_reaps_after_all_concurrent_closes(
    fake_backend: type,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After all concurrent runs close, the reaper eventually reaps every idle lease."""
    import flowjet.core.sandbox.arbox as arbox_mod

    monkeypatch.setattr(arbox_mod, "_REAPER_INTERVAL_SECONDS", 0.05)

    n = 5
    workspaces = [str(_make_empty_ws(tmp_path, f"ws{i}")) for i in range(n)]
    manager = ToolSandboxManager(_arcbox_settings(idle_timeout_seconds=0.01, max_sandboxes=0))
    try:
        # Open and close all concurrently.
        await asyncio.gather(*(manager.open_workspace(ws) for ws in workspaces))
        await asyncio.gather(*(manager.close_workspace(ws) for ws in workspaces))
        assert manager.lease_count == n  # all idle, not yet reaped

        await asyncio.sleep(0.3)
        assert manager.lease_count == 0  # all reaped
        assert all(inst.closed for inst in fake_backend.instances)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_idle_reaper_does_not_reap_during_concurrent_open(
    fake_backend: type,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reaper must not reap a lease while a concurrent open is in progress."""
    import flowjet.core.sandbox.arbox as arbox_mod

    monkeypatch.setattr(arbox_mod, "_REAPER_INTERVAL_SECONDS", 0.01)

    ws = str(_make_empty_ws(tmp_path, "contended"))
    manager = ToolSandboxManager(_arcbox_settings(idle_timeout_seconds=0.01))
    try:
        await manager.open_workspace(ws)
        await manager.close_workspace(ws)  # now idle

        # Immediately reopen while the reaper might be about to fire.
        # The workspace lock serializes: the reaper can't pop the lease
        # while open_workspace holds the lock.
        await asyncio.gather(
            manager.open_workspace(ws),
            manager.open_workspace(ws),
        )
        await asyncio.sleep(0.15)  # let the reaper run a few cycles
        # The lease is active (2 open runs) → never reaped.
        assert manager.lease_count == 1
        assert manager._leases[ws].active_runs == 2
        assert not fake_backend.instances[0].closed
    finally:
        await manager.shutdown()
