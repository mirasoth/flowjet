"""FLOWJET_WORKSPACE_WATCHED_SUBDIRS — Settings parsing and resolver wiring.

The setting flows: ``FLOWJET_WORKSPACE_WATCHED_SUBDIRS`` (comma-separated) →
``Settings.workspace_watched_subdirs_list()`` →
``SyncAwareWorkspaceResolver(watched_subdirs=...)`` →
``WorkspaceManager`` (pre-creates the subtrees at open, wires the DirtyTracker).
None/empty keeps the engine defaults — behavior unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowjet.core.runtime.isolation import SyncAwareWorkspaceResolver
from flowjet.server.config import Settings


def test_settings_watched_subdirs_list_none_and_blank() -> None:
    assert Settings(workspace_watched_subdirs=None).workspace_watched_subdirs_list() is None
    assert Settings(workspace_watched_subdirs="").workspace_watched_subdirs_list() is None
    assert Settings(workspace_watched_subdirs="  ").workspace_watched_subdirs_list() is None
    assert Settings(workspace_watched_subdirs=",, ").workspace_watched_subdirs_list() is None


def test_settings_watched_subdirs_list_parses_comma_entries() -> None:
    parsed = Settings(
        workspace_watched_subdirs="input, working ,output,deliverables"
    ).workspace_watched_subdirs_list()
    assert parsed == ["input", "working", "output", "deliverables"]


@pytest.mark.asyncio
async def test_resolver_watched_subdirs_precreated_and_wired(tmp_path: Path) -> None:
    """Configured subtrees are pre-created at open and reach the tracker."""
    resolver = SyncAwareWorkspaceResolver(
        tmp_path,
        sync_source=f"file://{tmp_path}/sync",
        cas_root=str(tmp_path / "cas"),
        watched_subdirs=("input", "working", "output", "deliverables"),
    )
    manager = resolver._ensure_manager()
    ws = await manager.open("run-1")

    assert (ws.root / "deliverables").is_dir()
    assert ws._dirty_tracker.watched_subdirs == (
        "input",
        "working",
        "output",
        "deliverables",
    )

    await manager.close("run-1")


@pytest.mark.asyncio
async def test_resolver_default_watched_subdirs_unchanged(tmp_path: Path) -> None:
    """Without the setting, only the engine defaults are created/wired."""
    resolver = SyncAwareWorkspaceResolver(
        tmp_path,
        sync_source=f"file://{tmp_path}/sync",
        cas_root=str(tmp_path / "cas"),
    )
    manager = resolver._ensure_manager()
    ws = await manager.open("run-2")

    assert not (ws.root / "deliverables").exists()
    assert ws._dirty_tracker.watched_subdirs == ("input", "working", "output")

    await manager.close("run-2")
