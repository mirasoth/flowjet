"""Load soothe-nano config for fj."""

from __future__ import annotations

from pathlib import Path

from soothe_nano.config import SOOTHE_HOME, SootheConfig


def default_config_path() -> Path:
    """Return ``~/.soothe/config/nano.yml`` (respects ``SOOTHE_HOME``)."""
    return SOOTHE_HOME / "config" / "nano.yml"


def load_config(config_path: str | Path | None = None) -> SootheConfig:
    """Load ``SootheConfig`` from YAML, or bootstrap from env when missing.

    Resolution order:
    1. Explicit ``config_path``
    2. ``SOOTHE_HOME / config / nano.yml`` (default ``~/.soothe/config/nano.yml``)
    3. ``SootheConfig()`` zero-config from ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``
    """
    path = Path(config_path).expanduser() if config_path else default_config_path()
    if path.is_file():
        return SootheConfig.from_yaml_file(str(path))
    if config_path is not None:
        raise FileNotFoundError(f"Config not found: {path}")
    return SootheConfig()
