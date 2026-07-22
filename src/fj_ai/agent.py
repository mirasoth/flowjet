"""Agent bootstrap, config load, builtin skills, and quiet CLI logging."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from soothe_nano import CodingCoreAgent, create_nano_agent
from soothe_nano.config import SOOTHE_HOME, SootheConfig
from soothe_nano.resolve import resolve_checkpointer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Builtin skills
# ---------------------------------------------------------------------------

_REGISTERED = False

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "builtin_skills"

# fj-only additions on top of soothe-nano's DEFAULT_CORE_SKILL_NAMES.
# Nano defaults (weather, github, clawhub, skill-creator) come from nano itself.
FJ_CORE_SKILL_NAMES: tuple[str, ...] = (
    "brainstorming",
    "requesting-code-review",
    "systematic-debugging",
    "using-superpowers",
)


def fj_core_skill_names() -> list[str]:
    """Nano default core skills plus fj high-traffic workflow skills."""
    from soothe_nano.skills.registry import DEFAULT_CORE_SKILL_NAMES

    return sorted(DEFAULT_CORE_SKILL_NAMES | {n.lower() for n in FJ_CORE_SKILL_NAMES})


def register_fj_builtin_skills() -> None:
    """Register ``fj_ai/builtin_skills`` as a soothe-nano builtin skill root.

    Idempotent — safe to call from multiple entry points. Requires
    ``soothe-nano>=0.9.9`` (``register_builtin_skill_root``).
    """
    global _REGISTERED
    if _REGISTERED:
        return
    if not BUILTIN_SKILLS_DIR.is_dir():
        return
    from soothe_nano.skills import register_builtin_skill_root

    register_builtin_skill_root(BUILTIN_SKILLS_DIR, source="builtin")
    _REGISTERED = True


# ---------------------------------------------------------------------------
# CLI logging
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Agent build
# ---------------------------------------------------------------------------


def ensure_workspace(workspace: Path | None = None) -> Path:
    """Use ``workspace`` or cwd as ``SOOTHE_WORKSPACE`` for file/shell tools."""
    root = (workspace or Path.cwd()).resolve()
    os.environ.setdefault("SOOTHE_WORKSPACE", str(root))
    try:
        from soothe_nano.workspace import FrameworkFilesystem

        FrameworkFilesystem.set_current_workspace(root)
    except Exception:  # pragma: no cover - optional API surface
        logger.debug("Could not set FrameworkFilesystem workspace", exc_info=True)
    return root


def apply_fj_defaults(config: SootheConfig) -> SootheConfig:
    """Apply fj CLI defaults without requiring them in ``nano.yml``.

    - SQLite checkpointer / durability
    - Disable soothe virtual mode (allow paths outside workspace)
    - Register fj package builtin skills
    - Core listing = nano defaults + a few fj workflow skills (rest deferred)
    """
    register_fj_builtin_skills()
    durability = config.agent.protocols.durability.model_copy(
        update={"backend": "sqlite", "checkpointer": "sqlite"}
    )
    protocols = config.agent.protocols.model_copy(update={"durability": durability})
    agent = config.agent.model_copy(update={"protocols": protocols})
    security = config.security.model_copy(update={"allow_paths_outside_workspace": True})
    persistence = config.persistence.model_copy(update={"default_backend": "sqlite"})
    progressive_skills = config.progressive_skills
    if progressive_skills.core_skills is None:
        progressive_skills = progressive_skills.model_copy(
            update={"core_skills": fj_core_skill_names()}
        )
    return config.model_copy(
        update={
            "agent": agent,
            "security": security,
            "persistence": persistence,
            "progressive_skills": progressive_skills,
        }
    )


# Backward-compatible alias used by older tests / imports.
_sqlite_config = apply_fj_defaults


@asynccontextmanager
async def open_sqlite_checkpointer(
    config: SootheConfig,
) -> AsyncIterator[Any | None]:
    """Yield an ``AsyncSqliteSaver`` using nano's default sqlite data path.

    Path: ``$SOOTHE_DATA_DIR/soothe_checkpoints.db`` (default ``~/.soothe/data/``).
    fj always uses sqlite for CLI threads, even if ``nano.yml`` prefers postgres.
    """
    sqlite_cfg = apply_fj_defaults(config)
    result = resolve_checkpointer(sqlite_cfg)
    db_path: str | None = None
    if isinstance(result, tuple):
        _placeholder, pool_or_path = result
        if isinstance(pool_or_path, str):
            db_path = pool_or_path

    if not db_path:
        logger.warning("SQLite checkpointer path unresolved; running without persistence")
        yield None
        return

    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from soothe_sdk.utils.serde import create_soothe_serde

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    checkpointer = AsyncSqliteSaver(conn, serde=create_soothe_serde())
    await checkpointer.setup()
    logger.debug("SQLite checkpointer ready at %s", db_path)
    try:
        yield checkpointer
    finally:
        await conn.close()


async def build_agent(
    config: SootheConfig,
    *,
    workspace: Path | None = None,
    checkpointer: Any | None = None,
    verbose: bool = False,
) -> CodingCoreAgent:
    """Build a full nano coding agent for the current workspace."""
    configure_cli_logging(verbose=verbose)
    ensure_workspace(workspace)
    agent = create_nano_agent(apply_fj_defaults(config))
    # Plugin imports (e.g. browser_use) may still attach root console handlers.
    silence_after_plugins(verbose=verbose)
    if checkpointer is not None:
        agent.graph.checkpointer = checkpointer
    return agent
