"""Tests for fj runtime config defaults."""

from __future__ import annotations

from soothe_nano.config import SootheConfig

from fj_ai.agent import apply_fj_defaults


def test_apply_fj_defaults_forces_sqlite() -> None:
    cfg = SootheConfig()
    cfg = cfg.model_copy(
        update={
            "persistence": cfg.persistence.model_copy(update={"default_backend": "postgresql"}),
        }
    )
    assert cfg.resolve_checkpointer_backend() == "postgresql"
    forced = apply_fj_defaults(cfg)
    assert forced.resolve_checkpointer_backend() == "sqlite"


def test_apply_fj_defaults_disables_virtual_mode() -> None:
    cfg = SootheConfig()
    assert cfg.security.allow_paths_outside_workspace is False
    forced = apply_fj_defaults(cfg)
    assert forced.security.allow_paths_outside_workspace is True
    # Nano derives: virtual_mode = not allow_paths_outside_workspace
    virtual_mode = not forced.security.allow_paths_outside_workspace
    assert virtual_mode is False
