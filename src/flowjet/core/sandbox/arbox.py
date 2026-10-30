"""ArcBox microVM lease lifecycle and host↔guest workspace staging."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shlex
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from flowjet.core.sandbox.settings import ToolSandboxSettings

logger = logging.getLogger(__name__)

# Host-side state dirs that never belong in the guest workspace.
_PUSH_SKIP_DIRS = frozenset({".workspace", "__pycache__", ".git"})
# Guest-side dirs that are never pulled back to the host workspace.
_PULL_SKIP_DIRS = frozenset({"__pycache__", ".git"})
_REAPER_INTERVAL_SECONDS = 5.0

# Sandbox labels: the only cross-process channel to the daemon, so crash
# recovery can tell "my VM", "a live peer's VM" and "a dead process's VM" apart.
_LABEL_MANAGED = "flowjet.sandbox"
_LABEL_OWNER = "flowjet.sandbox-owner"
_LABEL_INSTANCE = "flowjet.sandbox-instance"
_LABEL_WORKSPACE = "flowjet.sandbox-workspace"
_MANAGED_VALUE = "tool"

_HEARTBEAT_INTERVAL_SECONDS = 60.0
"""How often to re-arm the daemon-side orphan deadline on live leases."""

_STARTUP_SCAN_TIMEOUT_SECONDS = 15.0
"""Bound on the startup orphan scan; recovery is best effort, boot is not."""

_PROBE_COMMAND = "true"
"""Trivial guest command used as the readiness probe's guest tier.

The daemon's sandbox *records* outlive the VMs behind them: after a host
sleep, a machine restart or a daemon restart, `list()` still reports a
sandbox as ``ready`` while every call fails with ``VM not found``. That is a
control-plane fact, caught by the probe's first tier (``sandbox.info()``);
the guest command is the second tier, catching a wedged guest (VM present,
nothing executing).
"""

_PROBE_TIMEOUT_SECONDS = 20.0
"""Deadline for one readiness probe (the SDK kills the guest process group)."""

_PROBE_BRIDGE_GRACE_SECONDS = 5.0
"""Extra headroom over the probe deadline for the SDK round-trip itself."""

_INFO_PROBE_TIMEOUT_SECONDS = 10.0
"""Deadline for the control-plane tier of the readiness probe (one unary RPC)."""

_CONTROL_RPC_TIMEOUT_SECONDS = 15.0
"""Deadline for one control-plane lifecycle RPC (kill / set_lifecycle).

The SDK's per-RPC deadline is opt-in (``Connection(request_timeout)``) and the
manager does not configure it, so every lifecycle call needs its own bound: a
wedged call would otherwise stall the reaper loop — and a stalled heartbeat
reads to the daemon exactly like a dead owner, which gets *healthy* VMs
reaped at their deadlines.
"""

_TERMINAL_SANDBOX_STATES = frozenset({"stopping", "stopped", "failed"})
"""Guest states no turn can run in; a lease in one of them must be replaced."""


def _import_arcbox() -> Any:
    """Lazily import the external arcbox SDK with an actionable error."""
    try:
        import arcbox  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "sandbox.enabled=true in nano.yml requires the arcbox SDK, which ships "
            "transitively via soothe-nano (a dependency of soothe). Reinstall flowjet "
            "or run `arcbox serve` on the host. Remove the sandbox: section or set "
            "sandbox.enabled=false to run tools host-side."
        ) from exc
    return arcbox


@dataclass
class _SandboxLease:
    """One live guest VM bound to a host workspace path."""

    sandbox: Any
    backend: Any | None = None
    # Host-side snapshot: rel path -> (size, mtime_ns) at last successful
    # push/pull. Used to skip unchanged transfers.
    manifest: dict[str, tuple[int, int]] = field(default_factory=dict)
    active_runs: int = 0
    last_used: float = field(default_factory=time.monotonic)
    # Adopted from a previous process: pull the guest once before pushing, so
    # artifacts written by the crashed turn are recovered instead of clobbered.
    adopted: bool = False


def _format_bytes(n: int) -> str:
    """Human-readable byte count for operator-facing error messages."""
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _parse_df_available(output: str, root: str) -> int | None:
    """Available bytes from POSIX ``df`` output (``None`` when unparseable)."""
    for line in output.splitlines():
        fields = line.split()
        # POSIX df format: Filesystem 1B-blocks Used Available Use% Mounted-on
        if len(fields) >= 4 and fields[-1] == root:
            try:
                return int(fields[3])
            except ValueError:
                return None
    return None


class SandboxDiskFullError(RuntimeError):
    """The guest sandbox disk is below the configured free-space watermark.

    Raised by :meth:`ArcBoxToolSandboxManager.open_workspace` before the turn
    starts, so the failure surfaces as one readable turn error instead of a
    mid-run ENOSPC spiral the agent cannot fix on its own.
    """


class WorkspaceStager:
    """Host↔guest workspace file staging with (size, mtime) skip manifests.

    The host workspace directory stays the integration point (fsspec sync,
    backend materials). At session open the host tree is pushed into the
    guest ``workspace_root``; at close the guest tree is pulled back so the
    sync checkpoint and external readers still see agent outputs. Transfers
    skip files whose (size, mtime) match the manifest of the last transfer.
    """

    def __init__(self, settings: ToolSandboxSettings) -> None:
        self._settings = settings

    def guest_path(self, rel: Path) -> PurePosixPath:
        return PurePosixPath(self._settings.workspace_root) / PurePosixPath(*rel.parts)

    async def push(
        self,
        workspace: str,
        sandbox: Any,
        manifest: dict[str, tuple[int, int]],
    ) -> dict[str, tuple[int, int]]:
        """Upload the host workspace tree into the guest (skip unchanged).

        Returns the manifest for the next push.
        """
        root = Path(workspace)
        if not root.is_dir():
            logger.warning("Workspace %s does not exist; skipping sandbox push", workspace)
            return manifest
        pushed = 0
        next_manifest: dict[str, tuple[int, int]] = {}
        for item in sorted(root.rglob("*")):
            rel = item.relative_to(root)
            if any(part in _PUSH_SKIP_DIRS for part in rel.parts):
                continue
            if item.is_symlink():
                continue
            if item.is_dir():
                try:
                    await sandbox.files.mkdir(self.guest_path(rel))
                except Exception:  # noqa: BLE001
                    logger.debug("Sandbox mkdir failed for %s", rel, exc_info=True)
                continue
            if not item.is_file():
                continue
            stat = item.stat()
            snapshot = (stat.st_size, stat.st_mtime_ns)
            next_manifest[str(rel)] = snapshot
            if manifest.get(str(rel)) == snapshot:
                continue
            try:
                data = await asyncio.to_thread(item.read_bytes)
                await sandbox.files.write_bytes(self.guest_path(rel), data)
                pushed += 1
            except Exception:  # noqa: BLE001
                logger.warning("Sandbox push failed for %s", rel, exc_info=True)
        if pushed:
            logger.info("Sandbox push for %s: %d files", workspace, pushed)
        return next_manifest

    async def pull(
        self,
        workspace: str,
        sandbox: Any,
        manifest: dict[str, tuple[int, int]],
    ) -> dict[str, tuple[int, int]]:
        """Download the guest workspace tree back to the host (skip identical).

        Deletion propagation (RFC-RD-607 §4.4): files the agent deleted inside
        the guest are absent from its tree and are removed from the host too.
        Only paths recorded in the push manifest are eligible — host files
        created after the push are never in it, so they can never be deleted
        by this path. Returns the manifest for the next push.
        """
        root = Path(workspace)
        guest_root = PurePosixPath(self._settings.workspace_root)
        pulled = 0
        deleted = 0
        next_manifest: dict[str, tuple[int, int]] = {}
        guest_files: set[str] = set()

        async def walk(guest_dir: PurePosixPath, rel_dir: PurePosixPath) -> None:
            nonlocal pulled
            entries = await sandbox.files.list(guest_dir)
            for entry in entries:
                raw = PurePosixPath(entry.name)
                try:
                    # SDK entries carry the full guest path.
                    rel_entry = raw.relative_to(guest_root)
                except ValueError:
                    # Basename-only entries (defensive).
                    rel_entry = rel_dir / raw
                if any(part in _PULL_SKIP_DIRS for part in rel_entry.parts):
                    continue
                guest_path = guest_root / rel_entry
                if entry.kind == "directory":
                    await walk(guest_path, rel_entry)
                    continue
                if entry.kind != "file":
                    continue
                guest_files.add(rel_entry.as_posix())
                data = await sandbox.files.read_bytes(guest_path)
                dest = root / Path(*rel_entry.parts)
                if dest.is_file():
                    existing = await asyncio.to_thread(dest.read_bytes)
                    if existing == data:
                        stat = dest.stat()
                        next_manifest[str(rel_entry)] = (stat.st_size, stat.st_mtime_ns)
                        continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(dest.write_bytes, data)
                stat = dest.stat()
                next_manifest[str(rel_entry)] = (stat.st_size, stat.st_mtime_ns)
                pulled += 1

        await walk(guest_root, PurePosixPath("."))
        for rel in manifest:
            if rel in guest_files:
                continue
            dest = root / Path(*PurePosixPath(rel).parts)
            if not dest.is_file() or dest.is_symlink():
                continue
            try:
                await asyncio.to_thread(dest.unlink)
            except OSError:
                logger.warning("Sandbox pull: host delete failed for %s in %s", rel, workspace)
                continue
            deleted += 1
            parent = dest.parent
            while parent != root and parent.is_relative_to(root):
                if any(parent.iterdir()):
                    break
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        if pulled or deleted:
            logger.info(
                "Sandbox pull for %s: %d files pulled, %d guest deletions propagated",
                workspace,
                pulled,
                deleted,
            )
        return next_manifest


class ArcBoxToolSandboxManager:
    """Per-workspace ArcBox sandboxes for sandboxed tool execution.

    All async methods run on the server's main event loop (driven by the
    workspace resolver lifecycle hooks); :meth:`backend_for` is sync and may
    be called from pool worker threads.
    """

    def __init__(self, settings: ToolSandboxSettings) -> None:
        self._settings = settings
        self._stager = WorkspaceStager(settings)
        self._client: Any | None = None
        self._leases: dict[str, _SandboxLease] = {}
        self._locks_lock = asyncio.Lock()
        self._workspace_locks: dict[str, asyncio.Lock] = {}
        self._reaper_task: asyncio.Task[None] | None = None
        self._started = False
        # Identity of *this* process on the daemon: sandboxes carrying a
        # different instance id were left behind by a previous process.
        self._instance_id = uuid.uuid4().hex
        # Workspace key -> orphaned sandbox id, populated once at startup.
        self._recoverable: dict[str, str] = {}
        self._last_heartbeat = 0.0

    @property
    def settings(self) -> ToolSandboxSettings:
        return self._settings

    @property
    def lease_count(self) -> int:
        return len(self._leases)

    def validate_runtime(self) -> None:
        """Fail loud at startup when the SDK is missing (daemon is checked lazily)."""
        if self._settings.enabled:
            _import_arcbox()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_started(self) -> None:
        if self._started:
            return
        self._client = self._new_client()
        self._started = True
        # Recover what a previous process left behind *before* the first turn
        # can spawn a duplicate VM for the same workspace.
        await self._scan_orphans()
        self._reaper_task = asyncio.create_task(
            self._reap_idle(), name="arcbox-tool-sandbox-reaper"
        )
        max_sb = self._settings.effective_max_sandboxes()
        if max_sb == 0:
            cap_desc = "unlimited"
        elif self._settings.max_sandboxes is None:
            cap_desc = "computed"
        else:
            cap_desc = "explicit"
        logger.info(
            "ArcBox tool sandbox started: image=%s vcpus=%d mem_mib=%d max=%d (%s) network=%s",
            self._settings.image,
            self._settings.vcpus,
            self._settings.mem_mib,
            max_sb,
            cap_desc,
            self._settings.network,
        )

    def _new_client(self) -> Any:
        arcbox = _import_arcbox()
        connection_kwargs: dict[str, Any] = {}
        if self._settings.api_url:
            connection_kwargs["api_url"] = self._settings.api_url
        if self._settings.api_key:
            connection_kwargs["api_key"] = self._settings.api_key
        connection = arcbox.Connection(**connection_kwargs) if connection_kwargs else None
        return arcbox.AsyncArcBox(connection)

    async def _reconnect(self) -> None:
        """Drop the cached client and dial the daemon again (post-crash retry)."""
        old, self._client = self._client, None
        if old is not None:
            try:
                await old.aclose()
            except Exception:  # noqa: BLE001
                logger.debug("ArcBox client close during reconnect failed", exc_info=True)
        self._client = self._new_client()

    async def shutdown(self) -> None:
        reaper = self._reaper_task
        self._reaper_task = None
        if reaper is not None:
            reaper.cancel()
            try:
                await reaper
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        leases = list(self._leases.values())
        self._leases.clear()
        for lease in leases:
            await self._kill_lease(lease)
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                logger.warning("ArcBox client close failed", exc_info=True)
            self._client = None
        self._started = False

    async def _kill_lease(self, lease: _SandboxLease) -> None:
        try:
            await asyncio.wait_for(lease.sandbox.kill(), timeout=_CONTROL_RPC_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - best effort either way
            logger.warning("ArcBox sandbox kill failed", exc_info=True)

    async def _reap_idle(self) -> None:
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_SECONDS)
            try:
                await self._heartbeat()
                now = time.monotonic()
                stale = [
                    (key, lease)
                    for key, lease in self._leases.items()
                    if lease.active_runs == 0
                    and (now - lease.last_used) > self._settings.idle_timeout_seconds
                ]
                for key, lease in stale:
                    logger.info("ArcBox tool sandbox idle-recycled (workspace=%s)", key)
                    self._leases.pop(key, None)
                    await self._kill_lease(lease)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("ArcBox tool sandbox reaper error")

    async def _heartbeat(self) -> None:
        """Re-arm the daemon-side orphan deadline for every live lease.

        ``set_lifecycle(idle_timeout=...)`` restarts the countdown, so a lease
        whose owning process died stops being re-armed and the daemon destroys
        it after ``orphan_timeout_seconds``. That is crash cleanup with no
        cross-process coordination and no startup kill-list.

        A lease that cannot be re-armed is unreachable: drop it so the next
        turn spawns (or adopts) a usable sandbox instead of binding to a corpse.
        A lease with a run in flight is left in place — the per-turn probe will
        replace it, while dropping it now would skip that run's close-pull.
        """
        now = time.monotonic()
        if now - self._last_heartbeat < _HEARTBEAT_INTERVAL_SECONDS:
            return
        self._last_heartbeat = now
        for workspace, lease in list(self._leases.items()):
            try:
                await asyncio.wait_for(
                    lease.sandbox.set_lifecycle(
                        idle_timeout=self._settings.effective_orphan_timeout_seconds()
                    ),
                    timeout=_CONTROL_RPC_TIMEOUT_SECONDS,
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                if lease.active_runs > 0:
                    continue
                logger.warning(
                    "ArcBox heartbeat failed (workspace=%s, sandbox=%s); dropping lease",
                    workspace,
                    getattr(lease.sandbox, "id", "?"),
                    exc_info=True,
                )
                self._leases.pop(workspace, None)

    # ------------------------------------------------------------------
    # Crash recovery (restart of this process)
    # ------------------------------------------------------------------

    @staticmethod
    def _workspace_key(workspace: str) -> str:
        """Stable, label-safe fingerprint of a host workspace path."""
        return hashlib.sha256(workspace.encode()).hexdigest()[:16]

    def _labels(self, workspace: str) -> dict[str, str]:
        return {
            _LABEL_MANAGED: _MANAGED_VALUE,
            _LABEL_OWNER: self._settings.owner,
            _LABEL_INSTANCE: self._instance_id,
            _LABEL_WORKSPACE: self._workspace_key(workspace),
        }

    async def _scan_orphans(self) -> None:
        """Index sandboxes left behind by a previous process (best effort)."""
        if not self._settings.recover_orphans or self._client is None:
            return
        try:
            await asyncio.wait_for(self._collect_orphans(), timeout=_STARTUP_SCAN_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning("ArcBox orphan scan failed; restarting without recovery", exc_info=True)

    async def _collect_orphans(self) -> None:
        """List owner-scoped sandboxes that belong to another instance.

        Nothing is destroyed here: a rolling update may run two processes under
        one owner, and killing a live peer's VM would corrupt it. Unclaimed
        orphans are reaped by the daemon deadline instead.
        """
        assert self._client is not None
        async for summary in self._client.list(
            labels={_LABEL_MANAGED: _MANAGED_VALUE, _LABEL_OWNER: self._settings.owner}
        ):
            labels = getattr(summary, "labels", None) or {}
            # Re-check client-side: older daemons may ignore the filter.
            if labels.get(_LABEL_MANAGED) != _MANAGED_VALUE:
                continue
            if labels.get(_LABEL_OWNER) != self._settings.owner:
                continue
            if labels.get(_LABEL_INSTANCE) == self._instance_id:
                continue
            workspace_key = labels.get(_LABEL_WORKSPACE)
            if not workspace_key:
                continue
            self._recoverable[workspace_key] = summary.id
            logger.info(
                "ArcBox orphan sandbox available for recovery: %s (workspace=%s)",
                summary.id,
                workspace_key,
            )

    async def _adopt(self, workspace: str) -> _SandboxLease | None:
        """Reuse a sandbox left behind by a previous process, if it is alive.

        A crash leaves the VM running with whatever the interrupted turn had
        written but never pulled; adopting it recovers those files and avoids a
        cold boot. Returns ``None`` when there is no candidate or its VM is gone
        (in which case the daemon deadline reaps the stale record).
        """
        if not self._settings.recover_orphans or self._client is None:
            return None
        sandbox_id = self._recoverable.pop(self._workspace_key(workspace), None)
        if sandbox_id is None:
            return None
        try:
            sandbox = await self._client.connect(sandbox_id, timeout=self._settings.connect_timeout)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.info(
                "ArcBox orphan sandbox %s is no longer reachable; spawning a fresh one",
                sandbox_id,
            )
            return None
        lease = _SandboxLease(sandbox=sandbox, adopted=True)
        if not await self._lease_is_live(lease):
            await self._kill_lease(lease)
            return None
        self._leases[workspace] = lease
        logger.info(
            "ArcBox tool sandbox adopted after restart (workspace=%s, id=%s)",
            workspace,
            sandbox_id,
        )
        return lease

    async def _make_room_unlocked(self) -> None:
        """Evict least-recently-used idle sandboxes above the effective cap."""
        max_sandboxes = self._settings.effective_max_sandboxes()
        if max_sandboxes == 0:
            # Unlimited: no LRU eviction.
            return
        while len(self._leases) >= max_sandboxes:
            candidates = [
                (key, lease) for key, lease in self._leases.items() if lease.active_runs == 0
            ]
            if not candidates:
                # Every sandbox is busy: exceeding the cap is better than
                # deadlocking the request.
                logger.warning(
                    "ArcBox tool sandbox at max_sandboxes=%d with all sandboxes "
                    "busy; spawning an extra sandbox",
                    max_sandboxes,
                )
                return
            key, lease = min(candidates, key=lambda kv: kv[1].last_used)
            logger.info("ArcBox tool sandbox evicted for room (workspace=%s)", key)
            self._leases.pop(key, None)
            await self._kill_lease(lease)

    def _workspace_lock(self, workspace: str) -> asyncio.Lock:
        lock = self._workspace_locks.get(workspace)
        if lock is None:
            lock = asyncio.Lock()
            self._workspace_locks[workspace] = lock
        return lock

    # ------------------------------------------------------------------
    # Session lifecycle (main loop)
    # ------------------------------------------------------------------

    async def _lease_is_live(self, lease: _SandboxLease) -> bool:
        """Return ``True`` when the lease's guest is present and usable.

        Two tiers, cheap first:

        1. **Control plane** — ``sandbox.info()`` is one unary RPC, "always
           fresh, never cached", with no lifecycle side effects and no guest
           execution. It catches the observed failure class (the daemon's
           record outliving the VM: ``VM not found``) and terminal states.
        2. **Guest round-trip** — a trivial command catches a wedged guest
           (VM present, nothing executing). Commands run as independent
           process groups, so this never queues behind a peer's long-running
           command.

        Probing is the only way to tell "empty workspace" from "dead sandbox" —
        the difference between an agent that works and one that reports an
        empty workspace.
        """
        info = getattr(lease.sandbox, "info", None)
        if info is not None:
            try:
                snapshot = await asyncio.wait_for(info(), timeout=_INFO_PROBE_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - any failure means "not usable"
                logger.warning(
                    "ArcBox control-plane probe failed (sandbox=%s); the lease will be replaced",
                    getattr(lease.sandbox, "id", "?"),
                    exc_info=True,
                )
                return False
            state = str(getattr(snapshot, "state", "")).lower()
            if state in _TERMINAL_SANDBOX_STATES:
                logger.warning(
                    "ArcBox sandbox %s is in terminal state %r; the lease will be replaced",
                    getattr(lease.sandbox, "id", "?"),
                    state,
                )
                return False
        try:
            await asyncio.wait_for(
                lease.sandbox.commands.run(_PROBE_COMMAND, timeout=_PROBE_TIMEOUT_SECONDS),
                timeout=_PROBE_TIMEOUT_SECONDS + _PROBE_BRIDGE_GRACE_SECONDS,
            )
        except Exception:  # noqa: BLE001 - any failure means "not usable"
            logger.warning(
                "ArcBox readiness probe failed (sandbox=%s); the lease will be replaced",
                getattr(lease.sandbox, "id", "?"),
                exc_info=True,
            )
            return False
        return True

    async def open_workspace(self, workspace: str) -> None:
        """Ensure a *usable* sandbox for ``workspace`` and stage host files into it.

        Readiness invariant (once per turn, on the main loop, before the agent
        streams): a lease whose guest no longer answers is dropped, and every
        path that yields a new guest — spawn after a death, spawn after a
        restart, or adoption of a crashed process's VM — seeds it, so the agent
        never sees an empty workspace where the host has files.

        A reused lease with a peer turn mid-run keeps its guest state (fresher
        than the host copy) and skips the push, except right after a reseed:
        a fresh or adopted VM has no current state to protect.
        """
        await self._ensure_started()
        lock = self._workspace_lock(workspace)
        async with lock:
            lease = self._leases.get(workspace)
            carried_runs = 0
            seeded = False
            if lease is not None and not await self._lease_is_live(lease):
                # Runs still counted on the dead lease stay counted on its
                # replacement so peer open/close pairs stay balanced.
                carried_runs = lease.active_runs
                logger.warning(
                    "ArcBox tool sandbox for %s is gone (id=%s); respawning",
                    workspace,
                    lease.sandbox.id,
                )
                self._leases.pop(workspace, None)
                await self._kill_lease(lease)
                lease = None
            if lease is None:
                # After a restart the previous process's VM may still be alive
                # (and hold un-pulled artifacts): adopt it before spawning.
                lease = await self._adopt(workspace)
                seeded = lease is not None
            if lease is None:
                await self._make_room_unlocked()
                lease = await self._spawn(workspace)
                seeded = True
            if seeded:
                lease.active_runs = carried_runs
            lease.active_runs += 1
            lease.last_used = time.monotonic()
            if lease.active_runs > 1 and not seeded:
                # A peer session is mid-run on this sandbox: its guest state
                # is the freshest, a host push could clobber live edits.
                logger.debug(
                    "ArcBox tool sandbox: skipping host push for %s (%d active runs)",
                    workspace,
                    lease.active_runs,
                )
                return
            if lease.adopted:
                # Recover the crashed turn's guest writes first, then top up
                # from the host (materials uploaded while the process was down).
                lease.manifest = await self._stager.pull(workspace, lease.sandbox, {})
                lease.adopted = False
            lease.manifest = await self._stager.push(workspace, lease.sandbox, lease.manifest)
            await self._ensure_free_disk(workspace, lease)

    async def _ensure_free_disk(self, workspace: str, lease: _SandboxLease) -> None:
        """Refuse the turn when the guest disk is below the free-space watermark.

        The ArcBox daemon sizes the sandbox root disk from the guest image
        (content plus a small constant margin), so a write-heavy turn can
        fill the guest and leave the agent flailing in ENOSPC errors it
        cannot fix — its cleanup commands (`rm -rf /...`) hit the approval
        gate, and the turn dies with an opaque "tool failed". Failing fast
        here surfaces one readable error instead. The probe failing itself
        is warn-only (fail open): a broken probe must never block a turn.

        Accountancy note: ``active_runs`` was already incremented for this
        open, and a raise here means the caller's ``close_workspace`` never
        runs (``stream_run`` only closes after a successful open), so the
        increment is rolled back before raising.
        """
        threshold = self._settings.min_free_bytes
        if threshold <= 0:
            return
        backend = self.backend_for(workspace)
        free = await asyncio.to_thread(self._probe_free_bytes, backend)
        if free is None:
            logger.warning(
                "ArcBox guest disk probe failed (workspace=%s, sandbox=%s); "
                "continuing without the watermark check",
                workspace,
                lease.sandbox.id,
            )
            return
        if free >= threshold:
            return
        lease.active_runs = max(0, lease.active_runs - 1)
        message = (
            f"guest disk full: {self._settings.workspace_root} has "
            f"{_format_bytes(free)} free, below the {_format_bytes(threshold)} minimum "
            f"(sandbox.min_free_bytes). The ArcBox daemon sizes the sandbox root "
            f"disk from the guest image, so the workspace must be cleaned or the "
            f"sandbox disk enlarged before this turn can run."
        )
        raise SandboxDiskFullError(message)

    @staticmethod
    def _probe_free_bytes(backend: Any) -> int | None:
        """Guest free space at the workspace root, or ``None`` (fail open).

        Prefers soothe-nano's :meth:`ArcBoxBackend.free_space_bytes`; falls
        back to one ``df -B1 -P`` through ``execute`` for nano releases
        without the helper, so the watermark works against any nano ≥ 2.0.
        Never raises.
        """
        probe = getattr(backend, "free_space_bytes", None)
        if callable(probe):
            try:
                return probe()
            except Exception:  # noqa: BLE001 -- probe is best effort by contract
                logger.debug("ArcBox guest disk probe errored", exc_info=True)
                return None
        try:
            response = backend.execute(f"df -B1 -P {shlex.quote(backend.workspace_root)}")
        except Exception:  # noqa: BLE001 -- probe is best effort by contract
            logger.debug("ArcBox guest disk probe errored", exc_info=True)
            return None
        if response.exit_code not in (0, None):
            return None
        return _parse_df_available(response.output, backend.workspace_root)

    async def close_workspace(self, workspace: str) -> None:
        """Pull guest files back to the host workspace when the last run ends."""
        lock = self._workspace_lock(workspace)
        async with lock:
            lease = self._leases.get(workspace)
            if lease is None:
                return
            if lease.active_runs == 0:
                # Unbalanced close: no active run to end, nothing to pull.
                return
            lease.active_runs -= 1
            lease.last_used = time.monotonic()
            if lease.active_runs > 0:
                return
            try:
                lease.manifest = await self._stager.pull(workspace, lease.sandbox, lease.manifest)
            except Exception:  # noqa: BLE001
                # Best-effort: a failed pull must not fail the response, but
                # the sync checkpoint will miss guest-side outputs.
                logger.warning("ArcBox tool sandbox pull failed for %s", workspace, exc_info=True)

    async def _spawn(self, workspace: str) -> _SandboxLease:
        sandbox = await self._create(workspace)
        lease = _SandboxLease(sandbox=sandbox)
        self._leases[workspace] = lease
        logger.info("ArcBox tool sandbox ready (workspace=%s, id=%s)", workspace, sandbox.id)
        return lease

    async def _create(self, workspace: str) -> Any:
        """Create one guest with labels and a daemon-side orphan deadline.

        ``idle_timeout`` + ``on_idle="kill"`` is the crash backstop: if this
        process dies without cleaning up, the daemon destroys the VM once the
        deadline (re-armed by :meth:`_heartbeat`) expires. One reconnect retry
        covers a daemon that is itself restarting.
        """
        assert self._client is not None
        kwargs: dict[str, Any] = {
            "vcpus": self._settings.vcpus,
            "memory_mib": self._settings.mem_mib,
            "network": self._settings.network,
            "wait_until_ready": True,
            "labels": self._labels(workspace),
            "idle_timeout": self._settings.effective_orphan_timeout_seconds(),
            "on_idle": "kill",
        }
        try:
            return await self._client.create(self._settings.image, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning(
                "ArcBox sandbox create failed for %s; reconnecting and retrying once",
                workspace,
                exc_info=True,
            )
            await self._reconnect()
            assert self._client is not None
            return await self._client.create(self._settings.image, **kwargs)

    # ------------------------------------------------------------------
    # Agent binding (worker threads)
    # ------------------------------------------------------------------

    def sandbox_id_for(self, workspace: str) -> str | None:
        """Id of the guest currently bound to ``workspace`` (``None`` if unopened).

        This is the cache key adapters must use for a built agent: a reused
        lease keeps its id, while every replacement (idle recycle, dead VM,
        LRU eviction, respawn) yields a new one. "Same id" therefore means "the
        backend inside the cached agent still points at this live guest" —
        which a workspace path alone cannot tell, since it is stable across
        sandbox generations.
        """
        lease = self._leases.get(workspace)
        return lease.sandbox.id if lease is not None else None

    def backend_for(self, workspace: str) -> Any:
        """Return the :class:`ArcBoxBackend` bound to the workspace's sandbox.

        Sync and thread-safe: called from pool worker threads after
        :meth:`open_workspace` completed on the main loop. The backend is
        cached per lease and reused while the agent serves the workspace;
        because a respawn builds a new lease, callers holding a cached agent
        must compare :meth:`sandbox_id_for` and rebuild when it changed.
        """
        lease = self._leases.get(workspace)
        if lease is None:
            raise RuntimeError(
                f"no ArcBox sandbox open for workspace {workspace!r}; open_workspace must run first"
            )
        lease.last_used = time.monotonic()
        if lease.backend is None:
            from soothe_nano.sandbox import ArcBoxBackend

            lease.backend = ArcBoxBackend(
                sandbox_id=lease.sandbox.id,
                workspace_root=self._settings.workspace_root,
                default_timeout=self._settings.default_timeout,
                api_url=self._settings.api_url,
                api_key=self._settings.api_key,
                connect_timeout=self._settings.connect_timeout,
            )
        return lease.backend

    @property
    def guest_workspace(self) -> str:
        """Guest-side workspace path — what the agent sees as its workspace."""
        return self._settings.workspace_root


__all__ = [
    "ArcBoxToolSandboxManager",
    "SandboxDiskFullError",
    "WorkspaceStager",
]
