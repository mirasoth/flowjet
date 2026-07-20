"""fj-ai — thin CLI over soothe-nano."""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version("fj-ai")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]
