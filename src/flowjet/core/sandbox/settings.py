"""Flowjet-owned ``sandbox:`` settings parsed from the nano.yml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ToolSandboxSettings:
    """Flowjet-owned ``sandbox:`` keys parsed from the nano.yml.

    nano.yml keys owned by flowjet (unknown keys are ignored by
    ``SootheConfig``)::

        sandbox:
          enabled: true            # run tool calls in an arcbox container
          image: <image ref>       # guest image; must ship python3 + coreutils
          vcpus: 2
          mem_mib: 2048
          network: true
          workspace_root: /workspace
          default_timeout: 120
          connect_timeout: 60
          idle_timeout_seconds: 300
          max_sandboxes: 4
          api_url: null            # daemon connection; env fallback ARCBOX_API_URL
          api_key: null            # daemon credential; env fallback ARCBOX_API_KEY

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
    network: bool = True
    workspace_root: str = "/workspace"
    default_timeout: int = 120
    connect_timeout: float = 60.0
    idle_timeout_seconds: float = 300.0
    max_sandboxes: int = 4
    api_url: str | None = None
    api_key: str | None = None

    def __post_init__(self) -> None:
        if self.enabled and not (self.image and self.image.strip()):
            raise ValueError(
                "sandbox.enabled=true in nano.yml requires sandbox.image "
                "(the guest image reference, e.g. the flowjet-server image)."
            )
        if self.max_sandboxes < 1:
            raise ValueError("sandbox.max_sandboxes must be >= 1")
        if self.vcpus < 1:
            raise ValueError("sandbox.vcpus must be >= 1")
        if self.mem_mib < 128:
            raise ValueError("sandbox.mem_mib must be >= 128")


class SandboxSettingsLoader:
    """Load :class:`ToolSandboxSettings` from the nano config file."""

    @staticmethod
    def parse_section(section: Any) -> ToolSandboxSettings:
        """Parse the raw ``sandbox:`` mapping from nano.yml.

        Keys flowjet does not own (``on_deny``, ``placement_overrides``,
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
