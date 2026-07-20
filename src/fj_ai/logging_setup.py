"""Keep fj console I/O free of third-party INFO spam.

``browser_use`` configures the root logger to INFO on import (format
``%(levelname)-8s [%(name)s] %(message)s``). That leaks soothe-nano init
logs onto stderr whenever the browser_use plugin loads. fj disables that
side effect and strips any root console handlers that already landed.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_BROWSER_USE_SETUP_LOGGING = "BROWSER_USE_SETUP_LOGGING"


def configure_cli_logging() -> None:
    """Quiet the console for one-shot CLI use.

    - Opt out of ``browser_use`` import-time root logger setup when unset.
    - Remove existing root stream handlers (stderr/stdout) so init INFO
      lines do not interleave with the agent answer.
    """
    os.environ.setdefault(_BROWSER_USE_SETUP_LOGGING, "false")
    _remove_root_console_handlers()
    root = logging.getLogger()
    if root.level < logging.WARNING and not root.handlers:
        root.setLevel(logging.WARNING)


def silence_after_plugins() -> None:
    """Re-apply quieting after plugin imports (belt-and-suspenders)."""
    configure_cli_logging()


def _remove_root_console_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            continue
        if isinstance(handler, logging.FileHandler):
            continue
        if isinstance(handler, logging.StreamHandler):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - defensive
                pass
