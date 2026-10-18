"""ArcBox microVM lease lifecycle and host↔guest workspace staging."""

from __future__ import annotations

import asyncio
import logging
import time
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


def _import_arcbox() -> Any:
    """Lazily import the external arcbox SDK with an actionable error."""
    try:
        import arcbox  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "sandbox.enabled=true in nano.yml requires the external arcbox SDK "
            "(pip install arcbox, already part of the flowjet `server` extra) "
            "and the arcbox daemon running on the host (arcbox serve). The "
            "daemon manages microVMs via Hypervisor.framework (macOS) or KVM "
            "(Linux). Remove the sandbox: section or set sandbox.enabled=false "
            "to run tools host-side."
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

        Returns the manifest for the next push.
        """
        root = Path(workspace)
        guest_root = PurePosixPath(self._settings.workspace_root)
        pulled = 0
        next_manifest: dict[str, tuple[int, int]] = {}

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
        if pulled:
            logger.info("Sandbox pull for %s: %d files", workspace, pulled)
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
        arcbox = _import_arcbox()
        connection_kwargs: dict[str, Any] = {}
        if self._settings.api_url:
            connection_kwargs["api_url"] = self._settings.api_url
        if self._settings.api_key:
            connection_kwargs["api_key"] = self._settings.api_key
        connection = arcbox.Connection(**connection_kwargs) if connection_kwargs else None
        self._client = arcbox.AsyncArcBox(connection)
        self._started = True
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
            "ArcBox tool sandbox started: image=%s vcpus=%d mem_mib=%d max=%d "
            "(%s) network=%s",
            self._settings.image,
            self._settings.vcpus,
            self._settings.mem_mib,
            max_sb,
            cap_desc,
            self._settings.network,
        )

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
            await lease.sandbox.kill()
        except Exception:  # noqa: BLE001
            logger.warning("ArcBox sandbox kill failed", exc_info=True)

    async def _reap_idle(self) -> None:
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_SECONDS)
            try:
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

    async def open_workspace(self, workspace: str) -> None:
        """Ensure a sandbox for ``workspace`` and stage host files into it."""
        await self._ensure_started()
        lock = self._workspace_lock(workspace)
        async with lock:
            lease = self._leases.get(workspace)
            if lease is None:
                await self._make_room_unlocked()
                lease = await self._spawn(workspace)
            lease.active_runs += 1
            lease.last_used = time.monotonic()
            if lease.active_runs > 1:
                # A peer session is mid-run on this sandbox: its guest state
                # is the freshest, a host push could clobber live edits.
                logger.debug(
                    "ArcBox tool sandbox: skipping host push for %s (%d active runs)",
                    workspace,
                    lease.active_runs,
                )
                return
            lease.manifest = await self._stager.push(workspace, lease.sandbox, lease.manifest)

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
        assert self._client is not None
        sandbox = await self._client.create(
            self._settings.image,
            vcpus=self._settings.vcpus,
            memory_mib=self._settings.mem_mib,
            network=self._settings.network,
            wait_until_ready=True,
        )
        lease = _SandboxLease(sandbox=sandbox)
        self._leases[workspace] = lease
        logger.info("ArcBox tool sandbox ready (workspace=%s, id=%s)", workspace, sandbox.id)
        return lease

    # ------------------------------------------------------------------
    # Agent binding (worker threads)
    # ------------------------------------------------------------------

    def backend_for(self, workspace: str) -> Any:
        """Return the :class:`ArcBoxBackend` bound to the workspace's sandbox.

        Sync and thread-safe: called from pool worker threads after
        :meth:`open_workspace` completed on the main loop. The backend is
        cached per lease and reused while the agent serves the workspace.
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


__all__ = ["ArcBoxToolSandboxManager", "WorkspaceStager"]
