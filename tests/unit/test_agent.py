"""Tests for sqlite config forcing."""

from __future__ import annotations

from soothe_nano.config import SootheConfig

from fj_ai.agent import _sqlite_config


def test_sqlite_config_forces_backend() -> None:
    cfg = SootheConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": cfg.persistence.model_copy(update={"default_backend": "postgresql"}),
        }
    )
    assert cfg.resolve_checkpointer_backend() == "postgresql"
    forced = _sqlite_config(cfg)
    assert forced.resolve_checkpointer_backend() == "sqlite"
