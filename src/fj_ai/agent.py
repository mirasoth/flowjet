"""Create and wire a soothe-nano agent with fj runtime defaults."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from soothe_nano import CodingCoreAgent, create_nano_agent
from soothe_nano.config import SootheConfig
from soothe_nano.resolve import resolve_checkpointer

from fj_ai.logging_setup import configure_cli_logging, silence_after_plugins

logger = logging.getLogger(__name__)


def ensure_workspace(workspace: Path | None = None) -> Path:
    """Use ``workspace`` or cwd as ``SOOTHE_WORKSPACE`` for file/shell tools."""
    import os

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
    """
    durability = config.agent.protocols.durability.model_copy(
        update={"backend": "sqlite", "checkpointer": "sqlite"}
    )
    protocols = config.agent.protocols.model_copy(update={"durability": durability})
    agent = config.agent.model_copy(update={"protocols": protocols})
    security = config.security.model_copy(update={"allow_paths_outside_workspace": True})
    persistence = config.persistence.model_copy(update={"default_backend": "sqlite"})
    return config.model_copy(
        update={
            "agent": agent,
            "security": security,
            "persistence": persistence,
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
