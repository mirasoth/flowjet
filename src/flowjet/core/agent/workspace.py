"""Workspace env binding and sqlite checkpointer opening."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from soothe_nano.utils.resolver import resolve_checkpointer

logger = logging.getLogger(__name__)

# Treatments of the checkpointer policy that mean "do not persist".
_OFF_VALUES = frozenset({"", "off", "disabled", "none", "false", "0"})


def checkpointer_policy_enabled(policy: str | None) -> bool:
    """Whether a checkpointer policy string enables persistence."""
    return str(policy or "").strip().lower() not in _OFF_VALUES


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
    """Side persistence: an ``AsyncSqliteSaver`` on nano's sqlite data path."""

    @staticmethod
    @asynccontextmanager
    async def open_sqlite(config: Any) -> AsyncIterator[Any | None]:
        """Yield an ``AsyncSqliteSaver`` using nano's default sqlite data path.

        Path: ``$SOOTHE_DATA_DIR/databases/checkpoints.db`` (default
        ``~/.soothe/data/databases/checkpoints.db``). The config copy forces
        the sqlite backend so this works regardless of the durability settings
        (the CLI always runs sqlite).
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
        db_path = _sqlite_db_path(result)
        if not db_path:
            logger.warning("SQLite checkpointer path unresolved; running without persistence")
            yield None
            return

        saver = await _connect_sqlite(db_path)
        try:
            yield saver
        finally:
            await saver.conn.close()

    @staticmethod
    @asynccontextmanager
    async def open(config: Any) -> AsyncIterator[Any | None]:
        """Yield a checkpointer for the config's resolved durability backend.

        Server-surface counterpart of :meth:`open_sqlite`: honors
        ``agent.protocols.durability.checkpointer`` (which inherits
        ``persistence.default_backend``), so a deployment that asks for
        ``sqlite`` **or** ``postgresql`` gets thread state that survives across
        turns, pool workers and restarts.

        The PostgreSQL branch builds an ``AsyncPostgresSaver`` on nano's shared
        checkpoints pool so every worker and every restart sees the same
        threads — that is what makes ``conversation_key`` continuity (and
        recovery from an executor restart) work on this surface. Setup runs
        once per process under nano's advisory lock, so parallel workers cannot
        race LangGraph's DDL. Failure is degraded, not fatal: a warning is
        logged and ``None`` is yielded.
        """
        try:
            backend = str(config.resolve_checkpointer_backend()).strip().lower()
        except Exception:  # noqa: BLE001 - unknown config shape → sqlite default
            backend = "sqlite"

        if backend == "postgresql":
            try:
                saver = await _connect_postgres(config)
            except Exception:  # noqa: BLE001 - persistence is degraded, not fatal
                logger.warning(
                    "PostgreSQL checkpointer unavailable; thread state will not "
                    "persist across turns",
                    exc_info=True,
                )
                yield None
                return
            # The pool is a process-wide singleton shared by every worker:
            # closing it here would break the next turn.
            yield saver
            return

        if backend != "sqlite":
            logger.warning(
                "Checkpointer backend %r is not wired for the flowjet server "
                "surface; thread state will not persist across turns",
                backend,
            )
            yield None
            return

        result = resolve_checkpointer(config)
        db_path = _sqlite_db_path(result)
        if not db_path:
            logger.warning("SQLite checkpointer path unresolved; running without persistence")
            yield None
            return

        saver = await _connect_sqlite(db_path)
        try:
            yield saver
        finally:
            await saver.conn.close()


async def _connect_postgres(config: Any) -> Any:
    """Open an ``AsyncPostgresSaver`` on nano's shared checkpoints pool.

    ``resolve_checkpointer`` returns ``(None, pool)`` for PostgreSQL: the
    saver is built from that pool (not from a DSN), and the pool must be
    opened explicitly before use.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from soothe_nano.utils.serde import create_soothe_serde

    result = resolve_checkpointer(config)
    pool = result[1] if isinstance(result, tuple) else None
    if pool is None:
        raise RuntimeError("PostgreSQL checkpointer pool unresolved")

    await pool.open()
    saver = AsyncPostgresSaver(pool, serde=create_soothe_serde())
    await _setup_postgres(pool, saver)
    logger.debug("PostgreSQL checkpointer ready (shared pool)")
    return saver


async def _setup_postgres(pool: Any, saver: Any) -> None:
    """Run ``saver.setup()`` once per process under nano's advisory lock.

    Parallel `setup()` calls race LangGraph's DDL (``UniqueViolation`` on
    checkpoint types), so nano's helper serializes them — and it is a no-op
    after the first success in this process.
    """
    try:
        from soothe_nano.persistence.shared_checkpointer_pool import (
            SharedCheckpointerPool,
        )

        await SharedCheckpointerPool.setup_checkpointer(pool, saver.setup)
        return
    except (ImportError, AttributeError):  # pragma: no cover - older nano
        # nano without the helper (or without the method): plain setup().
        await saver.setup()


def _sqlite_db_path(result: Any) -> str | None:
    """Extract the sqlite db path from a ``resolve_checkpointer`` result."""
    if isinstance(result, tuple):
        _placeholder, pool_or_path = result
        if isinstance(pool_or_path, str):
            return pool_or_path
    return None


async def _connect_sqlite(db_path: str) -> Any:
    """Open one ``AsyncSqliteSaver`` connection on ``db_path``.

    WAL + busy timeout are load-bearing for the server: its thread pool opens
    one connection per worker onto the same file, and the default rollback
    journal would block readers behind writers and surface as
    ``database is locked``.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from soothe_nano.utils.serde import create_soothe_serde

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=5000")
    checkpointer = AsyncSqliteSaver(conn, serde=create_soothe_serde())
    await checkpointer.setup()
    logger.debug("SQLite checkpointer ready at %s", db_path)
    return checkpointer


__all__ = ["Checkpointers", "Workspaces", "checkpointer_policy_enabled"]
