"""Config loading — a ``SootheConfig`` that follows the selected backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from soothe_nano.config import SootheConfig

from flowjet.core.backend_config import Backend, resolve_backend
from flowjet.core.modes import Surface
from flowjet.home import default_config_path as _flowjet_config_path
from flowjet.home import ensure_flowjet_config


class FlowJetConfigLoader:
    """Load a :class:`SootheConfig` for a backend, or bootstrap from env.

    The config class follows the backend: ``soothe`` loads the *host*
    ``soothe.config.SootheConfig`` (a superset of nano's — the host agent reads
    host-owned fields such as ``agent.loop`` / ``agent.clarification`` that
    nano's config does not define), ``nano`` loads
    ``soothe_nano.config.SootheConfig``.

    Resolution order:

    1. Explicit ``config_path``
    2. ``$FLOWJET_HOME / config / nano.yml`` (default ``~/.flowjet/config/nano.yml``)
    3. Zero-config ``SootheConfig()`` from ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``

    On the ``soothe`` backend, a sibling ``soothe.yml`` (host-owned keys) is
    composed over ``nano.yml`` when present.

    Without an explicit ``config_path``, a config found in ``~/.soothe/config``
    is copied into the flowjet home first — see
    :func:`flowjet.home.ensure_flowjet_config`.
    """

    @staticmethod
    def default_path() -> Path:
        """Return ``$FLOWJET_HOME/config/nano.yml`` (default ``~/.flowjet/config/nano.yml``)."""
        return _flowjet_config_path()

    @classmethod
    def load(
        cls,
        config_path: str | Path | None = None,
        *,
        backend: Backend | None = None,
    ) -> Any:
        """Load a ``SootheConfig`` for ``backend``, or bootstrap from env when missing."""
        backend = backend or resolve_backend(Surface.CLI)
        if config_path is None:
            ensure_flowjet_config()
            path = cls.default_path()
        else:
            path = Path(config_path).expanduser()
        if path.is_file():
            return cls._load_file(path, backend)
        if config_path is not None:
            raise FileNotFoundError(f"Config not found: {path}")
        return cls.default(backend)

    @staticmethod
    def default(backend: Backend) -> Any:
        """Zero-config ``SootheConfig`` for ``backend`` (env-derived providers)."""
        if backend is Backend.SOOTHE:
            from soothe.config import SootheConfig as HostSootheConfig

            return HostSootheConfig()
        return SootheConfig()

    @staticmethod
    def _load_file(path: Path, backend: Backend) -> Any:
        """Parse ``path`` into the config class owned by ``backend``."""
        if backend is Backend.SOOTHE:
            from soothe.config import SootheConfig as HostSootheConfig

            host_path = path.with_name("soothe.yml")
            if host_path.is_file():
                return HostSootheConfig.from_split_yaml_files(
                    nano_path=str(path), soothe_path=str(host_path)
                )
            return HostSootheConfig.from_yaml_file(str(path))
        return SootheConfig.from_yaml_file(str(path))


__all__ = ["FlowJetConfigLoader"]
