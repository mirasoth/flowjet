"""``FLOWJET_HOME`` resolution for the config file.

FlowJet reads its config from ``$FLOWJET_HOME/config/nano.yml`` (default
``~/.flowjet/config/nano.yml``).  ``FLOWJET_HOME`` is the only authority for that
path; ``SOOTHE_HOME`` does not affect it, and soothe-owned state — CLI data,
logs, agents, plugins, sqlite databases — stays where the soothe runtime puts it.

This module is deliberately a stdlib-only leaf: it is imported from argparse
help builders (``fj -c``), so it must stay cheap, and it must not do file I/O
during import or inside :func:`default_config_path`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_FLOWJET_HOME = "~/.flowjet"


def flowjet_home() -> Path:
    """Return ``$FLOWJET_HOME`` (default ``~/.flowjet``), expanded.

    Read at call time, so callers can set the env var late.
    """
    raw = os.environ.get("FLOWJET_HOME") or DEFAULT_FLOWJET_HOME
    return Path(raw).expanduser()


def default_config_path() -> Path:
    """Return ``$FLOWJET_HOME/config/nano.yml``.

    Pure — no directory creation, no existence checks — because argparse help
    builders call it while rendering ``-h``.
    """
    return flowjet_home() / "config" / "nano.yml"
