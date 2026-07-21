"""Keep fj console I/O free of third-party INFO spam.

``browser_use`` configures the root logger to INFO on import (format
``%(levelname)-8s [%(name)s] %(message)s``). That leaks soothe-nano init
logs onto stderr whenever the browser_use plugin loads. fj disables that
side effect and strips any root console handlers that already landed.

Soothe's ``tool_error_handler`` logs failures with ``logger.exception``.
With no handlers configured, Python's ``lastResort`` handler would dump
full tracebacks to stderr. We attach a ``NullHandler`` (quiet) or a
compact one-line stderr handler (``verbose=True``) so tool errors stay
elegant on the TTY.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_BROWSER_USE_SETUP_LOGGING = "BROWSER_USE_SETUP_LOGGING"
_FJ_CONSOLE_HANDLER = "fj-console"


class _CompactConsoleFormatter(logging.Formatter):
    """One-line console records without exception tracebacks."""

    def formatException(self, ei: object) -> str:  # noqa: N802 - logging API
        return ""

    def format(self, record: logging.LogRecord) -> str:
        # logger.exception sets exc_info; drop it so format() stays one line.
        record.exc_info = None
        record.exc_text = None
        return super().format(record)


def configure_cli_logging(*, verbose: bool = False) -> None:
    """Quiet the console for one-shot CLI use.

    - Opt out of ``browser_use`` import-time root logger setup when unset.
    - Remove existing root stream handlers (stderr/stdout) so init INFO
      lines do not interleave with the agent answer.
    - Prevent ``lastResort`` traceback dumps from soothe tool failures.
    - When ``verbose``, show WARNING+ as single-line messages on stderr.
    """
    os.environ.setdefault(_BROWSER_USE_SETUP_LOGGING, "false")
    _remove_root_console_handlers()
    root = logging.getLogger()
    if verbose:
        handler = logging.StreamHandler(sys.stderr)
        handler.set_name(_FJ_CONSOLE_HANDLER)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(_CompactConsoleFormatter("%(message)s"))
        root.addHandler(handler)
    elif not root.handlers:
        null = logging.NullHandler()
        null.set_name(_FJ_CONSOLE_HANDLER)
        root.addHandler(null)
    if root.level < logging.WARNING:
        root.setLevel(logging.WARNING)


def silence_after_plugins(*, verbose: bool = False) -> None:
    """Re-apply quieting after plugin imports (belt-and-suspenders)."""
    configure_cli_logging(verbose=verbose)


def _remove_root_console_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            continue
        if isinstance(handler, logging.FileHandler):
            continue
        if isinstance(handler, logging.StreamHandler) or isinstance(handler, logging.NullHandler):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # pragma: no cover - defensive
                pass
