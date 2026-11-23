"""Sandbox lease lifecycle and host↔guest workspace staging.

The sandbox lifecycle (create/connect/kill) is owned by soothe-nano's
sandbox backend factory (:func:`~soothe_nano.sandbox.create_sandbox_backend`);
this module only manages the **pool** — one backend per workspace, LRU
eviction above the cap, idle reaping, host↔guest workspace staging, and the
disk watermark guard. No backend SDK symbols are imported here; flowjet is
backend-agnostic and delegates construction to nano's factory.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
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


def _format_bytes(n: int) -> str:
    """Human-readable byte count for operator-facing error messages."""
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


class SandboxDiskFullError(RuntimeError):
    """The guest sandbox disk is below the configured free-space watermark.

    Raised by :meth:`ToolSandboxManager.open_workspace` before the turn
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

    File operations go through the sandbox backend's ``execute()`` (for
    ``mkdir -p`` and ``find``-based listing) and ``upload_files()`` /
    ``download_files()`` (for byte transfers). No backend SDK types are used.
    """

    def __init__(self, settings: ToolSandboxSettings) -> None:
        self._settings = settings

    def guest_path(self, rel: Path) -> PurePosixPath:
        return PurePosixPath(self._settings.workspace_root) / PurePosixPath(*rel.parts)

    async def push(
        self,
        workspace: str,
        backend: Any,
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
        # Collect changed files and ensure guest directories exist.
        dirs_to_make: list[PurePosixPath] = []
        files_to_upload: list[tuple[str, bytes]] = []
        for item in sorted(root.rglob("*")):
            rel = item.relative_to(root)
            if any(part in _PUSH_SKIP_DIRS for part in rel.parts):
                continue
            if item.is_symlink():
                continue
            if item.is_dir():
                dirs_to_make.append(self.guest_path(rel))
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
                guest_p = str(self.guest_path(rel))
                files_to_upload.append((guest_p, data))
                pushed += 1
            except Exception:  # noqa: BLE001
                logger.warning("Sandbox push read failed for %s", rel, exc_info=True)
        # Create guest directories (best effort).
        for guest_dir in dirs_to_make:
            try:
                await asyncio.to_thread(
                    backend.execute, f"mkdir -p -- {shlex.quote(str(guest_dir))}"
                )
            except Exception:  # noqa: BLE001
                logger.debug("Sandbox mkdir failed for %s", guest_dir, exc_info=True)
        # Upload changed files in one batch.
        if files_to_upload:
            try:
                await asyncio.to_thread(backend.upload_files, files_to_upload)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Sandbox push upload failed for %d files", len(files_to_upload), exc_info=True
                )
        if pushed:
            logger.info("Sandbox push for %s: %d files", workspace, pushed)
        return next_manifest

    async def pull(
        self,
        workspace: str,
        backend: Any,
        manifest: dict[str, tuple[int, int]],
    ) -> dict[str, tuple[int, int]]:
        """Download the guest workspace tree back to the host (skip identical).

        Deletion propagation: files the agent deleted inside the guest are
        absent from its tree and are removed from the host too. Only paths
        recorded in the push manifest are eligible — host files created after
        the push are never in it, so they can never be deleted by this path.
        Returns the manifest for the next push.
        """
        root = Path(workspace)
        guest_root = PurePosixPath(self._settings.workspace_root)
        pulled = 0
        deleted = 0
        next_manifest: dict[str, tuple[int, int]] = {}
        guest_files: set[str] = set()

        # List the guest tree via execute() + find.
        try:
            listing = await asyncio.to_thread(
                backend.execute,
                f"find {shlex.quote(str(guest_root))} -type f -print0",
            )
            output = getattr(listing, "output", "") or ""
            exit_code = getattr(listing, "exit_code", 0)
        except Exception:  # noqa: BLE001
            logger.warning("Sandbox pull: guest listing failed for %s", workspace, exc_info=True)
            return manifest
        if exit_code not in (0, None):
            logger.warning("Sandbox pull: guest find failed (exit=%s) for %s", exit_code, workspace)
            return manifest

        raw_paths = [p for p in output.split("\0") if p]
        download_paths: list[str] = []
        for raw in raw_paths:
            try:
                rel_entry = PurePosixPath(raw).relative_to(guest_root)
            except ValueError:
                continue
            if any(part in _PULL_SKIP_DIRS for part in rel_entry.parts):
                continue
            guest_files.add(rel_entry.as_posix())
            download_paths.append(raw)

        # Download all guest files in one batch.
        contents: dict[str, bytes] = {}
        if download_paths:
            try:
                responses = await asyncio.to_thread(backend.download_files, download_paths)
                for resp in responses:
                    path = getattr(resp, "path", "")
                    content = getattr(resp, "content", None)
                    error = getattr(resp, "error", None)
                    if content is not None and not error:
                        contents[path] = content
            except Exception:  # noqa: BLE001
                logger.warning("Sandbox pull: download failed for %s", workspace, exc_info=True)

        for raw_path, data in contents.items():
            try:
                rel_entry = PurePosixPath(raw_path).relative_to(guest_root)
            except ValueError:
                continue
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

        # Propagate guest deletions to host (only for paths in the manifest).
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


@dataclass
class _SandboxLease:
    """One live sandbox backend bound to a host workspace path."""

    backend: Any
    # Host-side snapshot: rel path -> (size, mtime_ns) at last successful
    # push/pull. Used to skip unchanged transfers.
    manifest: dict[str, tuple[int, int]] = field(default_factory=dict)
    active_runs: int = 0
    last_used: float = field(default_factory=time.monotonic)


class ToolSandboxManager:
    """Per-workspace sandbox backends for sandboxed tool execution.

    Each workspace gets its own sandbox backend (created via nano's
    :func:`~soothe_nano.sandbox.create_sandbox_backend` factory), which
    manages the sandbox lifecycle (create/connect/kill) internally. This
    manager only handles the **pool**: LRU eviction above the cap, idle
    reaping, workspace staging, and the disk watermark guard.

    All async methods run on the server's main event loop (driven by the
    workspace resolver lifecycle hooks); :meth:`backend_for` is sync and may
    be called from pool worker threads.
    """

    def __init__(self, settings: ToolSandboxSettings) -> None:
        self._settings = settings
        self._stager = WorkspaceStager(settings)
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
        """Fail loud at startup when the sandbox config is invalid.

        The actual backend SDK availability check is deferred to nano's
        :func:`create_sandbox_backend` factory — flowjet does not import any
        backend SDK directly.
        """
        # Nothing to validate beyond what __post_init__ already checked.
        # The backend SDK presence is nano's concern (the factory raises if
        # the SDK is missing, and the builder falls back to host execution
        # with a warning).

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        self._reaper_task = asyncio.create_task(self._reap_idle(), name="tool-sandbox-reaper")
        max_sb = self._settings.effective_max_sandboxes()
        if max_sb == 0:
            cap_desc = "unlimited"
        elif self._settings.max_sandboxes is None:
            cap_desc = "computed"
        else:
            cap_desc = "explicit"
        logger.info(
            "Tool sandbox started: image=%s vcpus=%d mem_mib=%d max=%d (%s) network=%s",
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
            await self._close_lease(lease)
        self._started = False

    async def _close_lease(self, lease: _SandboxLease) -> None:
        """Close a lease's backend (destroys the sandbox if self-managed)."""
        try:
            close = getattr(lease.backend, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        except Exception:  # noqa: BLE001 - best effort
            logger.debug("Sandbox backend close failed", exc_info=True)

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
                    logger.info("Tool sandbox idle-recycled (workspace=%s)", key)
                    self._leases.pop(key, None)
                    await self._close_lease(lease)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Tool sandbox reaper error")

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

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
                    "Tool sandbox at max_sandboxes=%d with all sandboxes "
                    "busy; spawning an extra sandbox",
                    max_sandboxes,
                )
                return
            key, lease = min(candidates, key=lambda kv: kv[1].last_used)
            logger.info("Tool sandbox evicted for room (workspace=%s)", key)
            self._leases.pop(key, None)
            await self._close_lease(lease)

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
        """Ensure a *usable* sandbox for ``workspace`` and stage host files into it.

        Creates a sandbox backend via nano's factory on first open (the
        sandbox VM is created lazily on first ``execute``); reuses it on
        subsequent opens. The host tree is pushed into the guest
        ``workspace_root`` on a fresh lease; a reused lease with a peer turn
        mid-run keeps its guest state (fresher than the host copy) and skips
        the push.

        For ``os_sandbox`` (identity path mapping) staging is a no-op: the
        workspace is bound as-is (guest path == host path), so there is no
        host↔guest transfer. The backend's ``bind_workspace`` is called at
        spawn time instead.
        """
        await self._ensure_started()
        lock = self._workspace_lock(workspace)
        async with lock:
            lease = self._leases.get(workspace)
            if lease is None:
                await self._make_room_unlocked()
                lease = await self._spawn(workspace)
                seeded = True
            else:
                seeded = False
            lease.active_runs += 1
            lease.last_used = time.monotonic()
            if self._settings.is_os_sandbox:
                # Identity mapping: no push/pull. The workspace was bound at
                # spawn; nothing to stage.
                return
            if lease.active_runs > 1 and not seeded:
                # A peer session is mid-run on this sandbox: its guest state
                # is the freshest, a host push could clobber live edits.
                logger.debug(
                    "Tool sandbox: skipping host push for %s (%d active runs)",
                    workspace,
                    lease.active_runs,
                )
                return
            lease.manifest = await self._stager.push(workspace, lease.backend, lease.manifest)
            await self._ensure_free_disk(workspace, lease)

    async def _ensure_free_disk(self, workspace: str, lease: _SandboxLease) -> None:
        """Refuse the turn when the guest disk is below the free-space watermark.

        With native rootfs headroom (ArcBox daemon ``rootfs_headroom_mib``),
        the watermark is satisfied at birth for typical images. The probe
        failing itself is warn-only (fail open): a broken probe must never
        block a turn.

        Accountancy note: ``active_runs`` was already incremented for this
        open, and a raise here means the caller's ``close_workspace`` never
        runs (``stream_run`` only closes after a successful open), so the
        increment is rolled back before raising.
        """
        threshold = self._settings.min_free_bytes
        if threshold <= 0:
            return
        free = await asyncio.to_thread(self._probe_free_bytes, lease.backend)
        if free is None:
            logger.warning(
                "Tool sandbox guest disk probe failed (workspace=%s); "
                "continuing without the watermark check",
                workspace,
            )
            return
        if free >= threshold:
            return
        lease.active_runs = max(0, lease.active_runs - 1)
        message = (
            f"guest disk full: {self._settings.workspace_root} has "
            f"{_format_bytes(free)} free, below the {_format_bytes(threshold)} minimum "
            f"(sandbox.min_free_bytes). The sandbox root disk must be cleaned "
            f"or the headroom enlarged before this turn can run."
        )
        raise SandboxDiskFullError(message)

    @staticmethod
    def _probe_free_bytes(backend: Any) -> int | None:
        """Guest free space at the workspace root, or ``None`` (fail open).

        Uses the backend's ``free_space_bytes()`` helper (one ``df`` round-trip).
        Returns ``None`` when the probe itself fails so callers can fail open.
        Never raises.
        """
        probe = getattr(backend, "free_space_bytes", None)
        if not callable(probe):
            return None
        try:
            result: int | None = probe()
            return result
        except Exception:  # noqa: BLE001 -- probe is best effort by contract
            logger.debug("Sandbox guest disk probe errored", exc_info=True)
            return None

    async def close_workspace(self, workspace: str) -> None:
        """Pull guest files back to the host workspace when the last run ends.

        For ``os_sandbox`` (identity path mapping) the pull is a no-op: guest
        writes landed directly on the host filesystem, so there is nothing to
        transfer back.
        """
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
            if self._settings.is_os_sandbox:
                # Identity mapping: guest writes are already on the host.
                return
            try:
                lease.manifest = await self._stager.pull(workspace, lease.backend, lease.manifest)
            except Exception:  # noqa: BLE001
                # Best-effort: a failed pull must not fail the response, but
                # the sync checkpoint will miss guest-side outputs.
                logger.warning("Tool sandbox pull failed for %s", workspace, exc_info=True)

    async def _spawn(self, workspace: str) -> _SandboxLease:
        """Create a sandbox backend via nano's factory (backend-agnostic).

        Delegates to :func:`soothe_nano.sandbox.create_sandbox_backend` with
        the raw ``backend`` config from nano.yml. The factory dispatches to
        the registered backend (e.g. ArcBox, OsLocalSandbox) by ``type`` —
        flowjet never imports or calls a backend SDK directly.

        For ``os_sandbox`` the workspace is bound at spawn time via the
        backend's ``bind_workspace`` duck-typed extra (identity path mapping:
        guest path == host path).
        """
        from soothe_nano.config.models import SandboxBackendConfig
        from soothe_nano.sandbox import create_sandbox_backend

        backend_cfg = SandboxBackendConfig(**self._settings.backend)
        backend = create_sandbox_backend(backend_cfg)
        if self._settings.is_os_sandbox:
            binder = getattr(backend, "bind_workspace", None)
            if binder is not None:
                binder(workspace)
        lease = _SandboxLease(backend=backend)
        self._leases[workspace] = lease
        logger.info("Tool sandbox ready (workspace=%s)", workspace)
        return lease

    # ------------------------------------------------------------------
    # Agent binding (worker threads)
    # ------------------------------------------------------------------

    def sandbox_id_for(self, workspace: str) -> str | None:
        """Id of the guest currently bound to ``workspace`` (``None`` if unopened).

        This is the cache key adapters must use for a built agent: a reused
        lease keeps its id, while every replacement (idle recycle, LRU
        eviction) yields a new one. "Same id" therefore means "the backend
        inside the cached agent still points at this live guest" — which a
        workspace path alone cannot tell, since it is stable across sandbox
        generations.
        """
        lease = self._leases.get(workspace)
        if lease is None:
            return None
        # The backend's id property triggers lazy sandbox creation if needed.
        backend_id = getattr(lease.backend, "id", None)
        return str(backend_id) if backend_id is not None else None

    def backend_for(self, workspace: str) -> Any:
        """Return the sandbox backend bound to the workspace.

        Sync and thread-safe: called from pool worker threads after
        :meth:`open_workspace` completed on the main loop. The backend is
        cached per lease and reused while the agent serves the workspace;
        because a respawn builds a new lease, callers holding a cached agent
        must compare :meth:`sandbox_id_for` and rebuild when it changed.
        """
        lease = self._leases.get(workspace)
        if lease is None:
            raise RuntimeError(
                f"no sandbox open for workspace {workspace!r}; open_workspace must run first"
            )
        lease.last_used = time.monotonic()
        return lease.backend

    @property
    def guest_workspace(self) -> str:
        """Guest-side workspace path — what the agent sees as its workspace.

        For ``arcbox`` this is the in-guest mount point (e.g. ``/workspace``).
        For ``os_sandbox`` this returns the configured ``workspace_root``, but
        the real guest workspace is the host workspace path (identity mapping)
        — use :meth:`guest_workspace_for` to get the correct path per workspace.
        """
        return self._settings.workspace_root

    def guest_workspace_for(self, workspace: str) -> str:
        """The workspace path the agent should see for ``workspace``.

        For ``arcbox`` (and other VM-backed backends) this is the in-guest mount
        point — the same for every workspace. For ``os_sandbox`` (identity path
        mapping) the guest workspace *is* the host workspace path, so the agent
        sees the real directory it is operating on.
        """
        if self._settings.is_os_sandbox:
            return workspace
        return self._settings.workspace_root


__all__ = [
    "ToolSandboxManager",
    "SandboxDiskFullError",
    "WorkspaceStager",
]
