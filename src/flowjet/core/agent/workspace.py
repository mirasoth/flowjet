"""Workspace env binding and the CLI's sqlite checkpointer."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from soothe_nano.utils.resolver import resolve_checkpointer

logger = logging.getLogger(__name__)


class Workspaces:
    """Bind the workspace root used by file/shell tools."""

    @staticmethod
    def ensure(workspace: Path | None = None) -> Path:
        """Use ``workspace`` or cwd as ``SOOTHE_WORKSPACE`` for file/shell tools."""
        root = (workspace or Path.cwd()).resolve()
        os.environ.setdefault("SOOTHE_WORKSPACE", str(root))
        try:
            from soothe_nano.workspace import FrameworkFilesystem

            FrameworkFilesystem.set_current_workspace(root)
        except Exception:  # pragma: no cover - optional API surface
            logger.debug("Could not set FrameworkFilesystem workspace", exc_info=True)
        return root


class Checkpointers:
    """CLI-side persistence: an ``AsyncSqliteSaver`` on nano's data path."""

    @staticmethod
    @asynccontextmanager
    async def open_sqlite(config: Any) -> AsyncIterator[Any | None]:
        """Yield an ``AsyncSqliteSaver`` using nano's default sqlite data path.

        Path: ``$SOOTHE_DATA_DIR/soothe_checkpoints.db`` (default ``~/.soothe/data/``).
        """
        sqlite_cfg = config.model_copy(
            update={
                "agent": config.agent.model_copy(
                    update={
                        "protocols": config.agent.protocols.model_copy(
                            update={
                                "durability": config.agent.protocols.durability.model_copy(
                                    update={
                                        "backend": "sqlite",
                                        "checkpointer": "sqlite",
                                    }
                                )
                            }
                        )
                    }
                )
            }
        )
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
        from soothe_nano.utils.serde import create_soothe_serde

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(db_path)
        checkpointer = AsyncSqliteSaver(conn, serde=create_soothe_serde())
        await checkpointer.setup()
        logger.debug("SQLite checkpointer ready at %s", db_path)
        try:
            yield checkpointer
        finally:
            await conn.close()


__all__ = ["Checkpointers", "Workspaces"]
