"""Server-owned ``sandbox:`` settings parsed from the nano.yml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# When ``max_sandboxes`` is ``None``, the cap is computed from the host's
# logical CPU count and per-sandbox resource consumption. The formula reserves
# a configurable fraction of CPU headroom (default 70% usable) and divides by
# the per-sandbox vCPU allocation, then applies a hard minimum so small hosts
# still get a usable pool. The minimum also prevents pathological zero-cap
# results on single-core CI runners.
_COMPUTED_MAX_SANDBOXES_MIN = 8
_DEFAULT_CPU_USABLE_FRACTION = 0.70

# Env var names for operator overrides without editing nano.yml.
#   FLOWJET_SANDBOX_MAX          → fixed int cap (0 = unlimited)
#   FLOWJET_SANDBOX_MAX_PERCENT  → percentage of host CPU usable (1–100,
#                                  default 70); applies only when max is None.
_ENV_MAX_SANDBOXES = "FLOWJET_SANDBOX_MAX"
_ENV_MAX_SANDBOXES_PERCENT = "FLOWJET_SANDBOX_MAX_PERCENT"


def _env_cpu_usable_fraction() -> float:
    """Read ``FLOWJET_SANDBOX_MAX_PERCENT`` (1–100, default 70)."""
    raw = os.environ.get(_ENV_MAX_SANDBOXES_PERCENT)
    if not raw:
        return _DEFAULT_CPU_USABLE_FRACTION
    try:
        pct = int(raw.strip())
    except ValueError:
        return _DEFAULT_CPU_USABLE_FRACTION
    if pct < 1 or pct > 100:
        return _DEFAULT_CPU_USABLE_FRACTION
    return pct / 100.0


def compute_max_sandboxes(
    vcpus: int,
    *,
    cpu_count: int | None = None,
    usable_fraction: float | None = None,
) -> int:
    """Compute a dynamic sandbox cap from host CPU and per-sandbox vCPUs.

    The host keeps ``1 - usable_fraction`` CPU headroom (default 30%); the
    usable core budget is divided by the per-sandbox ``vcpus`` allocation to
    get the concurrent sandbox count. A hard floor of
    :data:`_COMPUTED_MAX_SANDBOXES_MIN` keeps small hosts (including CI runners)
    usable.

    >>> compute_max_sandboxes(2, cpu_count=8)
    8
    >>> compute_max_sandboxes(4, cpu_count=32)
    8
    >>> compute_max_sandboxes(2, cpu_count=32)
    11
    """
    if vcpus < 1:
        raise ValueError("vcpus must be >= 1")
    if usable_fraction is None:
        usable_fraction = _env_cpu_usable_fraction()
    if cpu_count is None:
        cpu_count = os.cpu_count() or 1
    usable = max(1, int(cpu_count * usable_fraction))
    computed = max(1, usable // vcpus)
    return max(computed, _COMPUTED_MAX_SANDBOXES_MIN)


@dataclass(slots=True)
class ToolSandboxSettings:
    """Server-owned ``sandbox:`` keys parsed from the nano.yml.

    nano.yml keys owned by the server (unknown keys are ignored by
    ``SootheConfig``)::

        sandbox:
          enabled: true            # run tool calls in an arcbox container
          image: <image ref>       # guest image; must ship python3 + coreutils
          vcpus: 2
          mem_mib: 2048
          network: false           # guest egress; OFF by default
          workspace_root: /workspace
          default_timeout: 120
          connect_timeout: 60
          idle_timeout_seconds: 300
          max_sandboxes: 8         # 0 (unlimited), None (compute from host CPU), or int
          orphan_timeout_seconds: null  # daemon-side crash deadline; None derives it
          recover_orphans: true    # adopt surviving VMs after a restart
          owner: flowjet           # sandbox label namespace; env FLOWJET_SANDBOX_OWNER
          api_url: null            # daemon connection; env fallback ARCBOX_API_URL
          api_key: null            # daemon credential; env fallback ARCBOX_API_KEY
          min_free_bytes: 0        # refuse turns when guest free space < this (0 = off)

    The remaining ``sandbox:`` keys (``on_deny`` / ``placement_overrides`` /
    ``max_shuttle_bytes``) belong to soothe-nano's placement policy and are
    consumed by the agent build itself.
    """

    enabled: bool = False
    # Guest image reference; must ship python3 + POSIX coreutils (the nano
    # sandbox derives file ops from guest-side execute).
    image: str | None = None
    vcpus: int = 2
    mem_mib: int = 2048
    # Guest egress. OFF by default: `true` NATs the guest through the ArcBox
    # host with no per-destination policy (the daemon only knows ENABLED|NONE),
    # so everything the host can route to — internal network and VPN included —
    # becomes reachable from agent shell commands. Web access is not lost: the
    # web tools are host-placement and never run in the guest.
    network: bool = False
    workspace_root: str = "/workspace"
    default_timeout: int = 120
    connect_timeout: float = 60.0
    idle_timeout_seconds: float = 300.0
    # Default cap of 8 sandboxes. ``0`` means unlimited — no LRU eviction.
    # ``None`` means compute from host CPU (70% usable, overridable via
    # ``FLOWJET_SANDBOX_MAX_PERCENT``) and per-sandbox vCPUs, with a hard
    # minimum of 8. A positive int pins the cap explicitly. The env var
    # ``FLOWJET_SANDBOX_MAX`` (int, 0=unlimited) overrides YAML at load time.
    max_sandboxes: int | None = 8

    # Daemon-side deadline for a sandbox whose owner stopped talking to it.
    # A crashed flowjet-server cannot clean up its VMs, so every sandbox is
    # created with ``idle_timeout=<orphan deadline>`` + ``on_idle="kill"``
    # and the manager re-arms that timer while it is alive: expiry therefore
    # means "the process that owned this sandbox is gone". ``None`` (the
    # default) derives ``max(900, 3 × idle_timeout_seconds)`` so a long idle
    # reaper can never be preempted by a daemon kill, and existing configs
    # without this key keep parsing unchanged; an explicit value must exceed
    # ``idle_timeout_seconds`` (checked only when the sandbox is enabled).
    orphan_timeout_seconds: float | None = None
    # Adopt sandboxes left behind by a previous process (crash / restart) and
    # pull their guest state before reusing them. Assumes one flowjet process
    # serves a given workspace at a time (the shipped deployment runs a single
    # agentspace-flowjet replica); disable to always start from a fresh VM.
    recover_orphans: bool = True
    # Label namespace so several flowjet planes sharing one daemon never
    # recover or reap each other's sandboxes.
    owner: str = "flowjet"

    # Disk watermark: refuse to open a sandbox whose guest has less free
    # space than this (bytes) at session open. The ArcBox daemon sizes the
    # sandbox root disk from the guest image plus a small constant margin,
    # so a write-heavy turn can fill the guest and leave the agent flailing
    # in ENOSPC errors it cannot fix (its cleanup commands hit the approval
    # gate). Guarding here turns that spiral into one readable turn error.
    # ``0`` (the default) disables the probe.
    min_free_bytes: int = 0

    api_url: str | None = None
    api_key: str | None = None

    def __post_init__(self) -> None:
        if self.enabled and not (self.image and self.image.strip()):
            raise ValueError(
                "sandbox.enabled=true in nano.yml requires sandbox.image "
                "(the guest image reference, e.g. the server image)."
            )
        if self.max_sandboxes is not None and self.max_sandboxes < 0:
            raise ValueError(
                "sandbox.max_sandboxes must be a non-negative int (0 = unlimited) or None"
            )
        if self.min_free_bytes < 0:
            raise ValueError("sandbox.min_free_bytes must be a non-negative int (0 = disabled)")
        if self.vcpus < 1:
            raise ValueError("sandbox.vcpus must be >= 1")
        if self.mem_mib < 128:
            raise ValueError("sandbox.mem_mib must be >= 128")
        if not self.owner:
            self.owner = os.environ.get("FLOWJET_SANDBOX_OWNER", "flowjet")
        if self.orphan_timeout_seconds is not None:
            if self.orphan_timeout_seconds <= 0:
                raise ValueError("sandbox.orphan_timeout_seconds must be > 0")
            if self.enabled and self.orphan_timeout_seconds <= self.idle_timeout_seconds:
                raise ValueError(
                    "sandbox.orphan_timeout_seconds must exceed idle_timeout_seconds "
                    "(the daemon-side crash deadline must never preempt the idle reaper)"
                )

    def effective_orphan_timeout_seconds(self) -> float:
        """Resolve the daemon-side crash deadline (``None`` derives it).

        Derived as ``max(900, 3 × idle_timeout_seconds)``: high enough that a
        sandbox the process still holds is never daemon-killed between
        heartbeats, low enough that an orphan is reaped in bounded time.
        """
        if self.orphan_timeout_seconds is not None:
            return self.orphan_timeout_seconds
        return max(900.0, self.idle_timeout_seconds * 3.0)

    def effective_max_sandboxes(self, *, cpu_count: int | None = None) -> int:
        """Resolve the sandbox cap: env override, explicit int, None, or unlimited.

        Resolution order (highest priority first):
        1. ``FLOWJET_SANDBOX_MAX`` env var (int; ``0`` = unlimited → returns 0)
        2. Explicit ``max_sandboxes`` int (``0`` = unlimited → returns 0)
        3. ``None`` → computed from host CPU and per-sandbox vCPUs

        Returns ``0`` when the cap is unlimited; callers must treat ``0`` as
        "no LRU eviction" (see :meth:`ArcBoxToolSandboxManager._make_room`).

        ``cpu_count`` is injectable for deterministic tests; production reads
        :func:`os.cpu_count`.
        """
        resolved = self._resolve_max_sandboxes()
        if resolved == 0:
            return 0  # unlimited
        if resolved is not None:
            return resolved
        return compute_max_sandboxes(self.vcpus, cpu_count=cpu_count)

    def _resolve_max_sandboxes(self) -> int | None:
        """Return the raw cap from env override or field, or ``None`` for compute."""
        env_raw = os.environ.get(_ENV_MAX_SANDBOXES)
        if env_raw:
            token = env_raw.strip().lower()
            if token in ("none", "null"):
                return None
            try:
                return int(token)
            except ValueError:
                pass  # fall through to field value
        return self.max_sandboxes


class SandboxSettingsLoader:
    """Load :class:`ToolSandboxSettings` from the nano config file."""

    @staticmethod
    def parse_section(section: Any) -> ToolSandboxSettings:
        """Parse the raw ``sandbox:`` mapping from nano.yml.

        Keys the server does not own (``on_deny``, ``placement_overrides``,
        ``max_shuttle_bytes``) are ignored here — they stay in the loaded
        ``SootheConfig`` and reach the agent build unchanged.
        """
        if not isinstance(section, dict):
            return ToolSandboxSettings()
        known = {
            f
            for f in ToolSandboxSettings.__dataclass_fields__  # type: ignore[attr-defined]
        }
        values = {k: section[k] for k in section if k in known}
        # ``max_sandboxes: None`` in YAML parses as the string "none"; map
        # that to ``None`` so :meth:`effective_max_sandboxes` computes the cap.
        # ``max_sandboxes: 0`` means unlimited (no LRU eviction).
        if isinstance(values.get("max_sandboxes"), str):
            token = values["max_sandboxes"].strip().lower()
            if token in ("none", "null"):
                values["max_sandboxes"] = None
            else:
                # Accept a numeric string for YAML robustness (incl. 0).
                values["max_sandboxes"] = int(token)
        return ToolSandboxSettings(**values)

    @classmethod
    def load(cls, config_path: str | Path | None) -> ToolSandboxSettings:
        """Load the tool-sandbox settings from the nano config file.

        Resolution mirrors :meth:`flowjet.core.agent.config.FlowJetConfigLoader.load`:
        an explicit path must exist; without one the default
        ``$FLOWJET_HOME/config/nano.yml`` is used when present. No config file
        at all means the sandbox is disabled.
        """
        if config_path is not None:
            path = Path(config_path).expanduser()
            if not path.is_file():
                raise FileNotFoundError(f"Config not found: {path}")
        else:
            from flowjet.home import default_config_path

            path = default_config_path()
            if not path.is_file():
                return ToolSandboxSettings()

        import yaml

        try:
            with path.open() as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
        if not isinstance(raw, dict):
            return ToolSandboxSettings()
        return cls.parse_section(raw.get("sandbox"))


__all__ = ["SandboxSettingsLoader", "ToolSandboxSettings"]
