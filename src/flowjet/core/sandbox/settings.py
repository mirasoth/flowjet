"""Server-owned ``sandbox:`` settings parsed from the nano.yml.

The sandbox lifecycle (create/connect/kill) is owned by soothe-nano's
sandbox backend factory (via :func:`create_sandbox_backend`); flowjet
only reads the config fields it needs for **pool management** (LRU
eviction, idle reaping, workspace staging, disk watermark) and passes
the full ``backend`` config to nano at backend construction time. No
backend SDK symbols are imported or called here — flowjet is
backend-agnostic and delegates construction to nano's
:class:`~soothe_nano.sandbox.SandboxBackendFactory`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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

    Uses the **multi-backend config format** (breaking change from the old
    flat ``image`` / ``vcpus`` / etc. fields). The ``backend`` dict is passed
    verbatim to nano's :func:`~soothe_nano.sandbox.create_sandbox_backend`,
    which dispatches to the registered factory by ``type``::

        sandbox:
          enabled: true
          max_sandboxes: 8         # pool cap (0=unlimited, None=compute)
          min_free_bytes: 0        # disk watermark (0 = off)
          idle_timeout_seconds: 300
          backend:
            type: arcbox
            arcbox:
              image: <image ref>    # guest image; must ship python3 + coreutils
              vcpus: 2
              mem_mib: 2048
              network: false        # guest egress; OFF by default
              workspace_root: /workspace
              default_timeout: 120
              connect_timeout: 60
              idle_timeout_seconds: 300
              # ... other backend-specific fields

    Pool-management fields (``max_sandboxes``, ``min_free_bytes``,
    ``idle_timeout_seconds``) live at the ``sandbox:`` top level because they
    are backend-agnostic. Backend-specific lifecycle fields live under
    ``sandbox.backend.<type>`` and are opaque to flowjet — it passes them
    through to nano's factory unchanged.

    The sandbox lifecycle (create/connect/kill) is delegated to nano's
    :func:`create_sandbox_backend` via the ``backend`` config; flowjet only
    manages the **pool** (LRU eviction, idle reaping, workspace staging, disk
    watermark). No backend SDK symbols are imported here.
    """

    enabled: bool = False
    # Raw backend config dict — passed verbatim to nano's factory. Contains
    # ``type`` + the backend-specific sub-config (e.g. ``arcbox: {...}``).
    backend: dict[str, Any] = field(default_factory=dict)
    # Pool cap: ``0`` = unlimited (no LRU eviction), ``None`` = compute from
    # host CPU, positive int = explicit cap. Env override:
    # ``FLOWJET_SANDBOX_MAX`` (int, 0=unlimited).
    max_sandboxes: int | None = 8
    # Disk watermark: refuse to open a sandbox whose guest has less free
    # space than this (bytes) at session open. ``0`` disables the probe.
    min_free_bytes: int = 0
    # Idle reaper: destroy a sandbox whose last-used timestamp is older than
    # this (seconds). Also read from the backend config as a fallback for
    # logging when the backend defines its own idle timeout.
    idle_timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.enabled and not self.backend:
            raise ValueError(
                "sandbox.enabled=true in nano.yml requires sandbox.backend "
                "(e.g. type: arcbox + arcbox: {...})"
            )
        if self.max_sandboxes is not None and self.max_sandboxes < 0:
            raise ValueError(
                "sandbox.max_sandboxes must be a non-negative int (0 = unlimited) or None"
            )
        if self.min_free_bytes < 0:
            raise ValueError("sandbox.min_free_bytes must be a non-negative int (0 = disabled)")

    # ------------------------------------------------------------------
    # Backend config accessors (read-through to the raw dict)
    # ------------------------------------------------------------------

    @property
    def backend_type(self) -> str:
        """The backend type discriminator (e.g. ``"arcbox"``)."""
        return str(self.backend.get("type", "arcbox"))

    @property
    def _backend_config(self) -> dict[str, Any]:
        """The backend-specific sub-config (e.g. ``arcbox: {...}``)."""
        sub = self.backend.get(self.backend_type, {})
        return dict(sub) if isinstance(sub, dict) else {}

    @property
    def image(self) -> str | None:
        """Guest image reference from the backend config (for logging)."""
        return self._backend_config.get("image")

    @property
    def vcpus(self) -> int:
        """Per-sandbox vCPU allocation from the backend config (for logging/cap)."""
        return int(self._backend_config.get("vcpus", 2))

    @property
    def mem_mib(self) -> int:
        """Per-sandbox memory (MiB) from the backend config (for logging)."""
        return int(self._backend_config.get("mem_mib", 2048))

    @property
    def network(self) -> bool:
        """Guest network egress from the backend config (for logging)."""
        return bool(self._backend_config.get("network", False))

    @property
    def workspace_root(self) -> str:
        """Guest workspace root path from the backend config (for staging)."""
        return str(self._backend_config.get("workspace_root", "/workspace"))

    @property
    def default_timeout(self) -> int:
        """Fallback execute timeout from the backend config."""
        return int(self._backend_config.get("default_timeout", 120))

    @property
    def connect_timeout(self) -> float:
        """Connect timeout from the backend config."""
        return float(self._backend_config.get("connect_timeout", 60.0))

    @property
    def backend_idle_timeout_seconds(self) -> float:
        """Idle timeout from the backend config (for the reaper)."""
        return float(self._backend_config.get("idle_timeout_seconds", self.idle_timeout_seconds))

    def effective_max_sandboxes(self, *, cpu_count: int | None = None) -> int:
        """Resolve the sandbox cap: env override, explicit int, None, or unlimited.

        Resolution order (highest priority first):
        1. ``FLOWJET_SANDBOX_MAX`` env var (int; ``0`` = unlimited → returns 0)
        2. Explicit ``max_sandboxes`` int (``0`` = unlimited → returns 0)
        3. ``None`` → computed from host CPU and per-sandbox vCPUs

        Returns ``0`` when the cap is unlimited; callers must treat ``0`` as
        "no LRU eviction" (see :meth:`ToolSandboxManager._make_room`).

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

        Reads the new multi-backend format (``sandbox.backend.type`` +
        ``sandbox.backend.<type>``). Pool-management keys (``max_sandboxes``,
        ``min_free_bytes``, ``idle_timeout_seconds``) are read from the
        ``sandbox:`` top level. The remaining ``sandbox:`` keys (``on_deny``,
        ``placement_overrides``, ``max_shuttle_bytes``) belong to soothe-nano's
        placement policy and stay in the loaded ``SootheConfig`` — flowjet
        never reads them.
        """
        if not isinstance(section, dict):
            return ToolSandboxSettings()
        # Pool-management fields owned by flowjet.
        pool_keys = {"max_sandboxes", "min_free_bytes", "idle_timeout_seconds"}
        values: dict[str, Any] = {}
        for k in ("enabled", "backend", *pool_keys):
            if k in section:
                values[k] = section[k]
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
