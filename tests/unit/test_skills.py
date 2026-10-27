"""Tests for fj builtin skill registration."""

from __future__ import annotations

from soothe_nano.config import SootheConfig
from soothe_nano.skills.builtins import SkillRoots
from soothe_nano.skills.index import SkillIndex

from flowjet.cli.agent import BUILTIN_SKILLS_DIR, apply_fj_defaults, register_fj_builtin_skills


def test_builtin_skills_dir_has_skill_md() -> None:
    skill_mds = list(BUILTIN_SKILLS_DIR.glob("*/SKILL.md"))
    assert skill_mds, f"expected skills under {BUILTIN_SKILLS_DIR}"
    names = {p.parent.name for p in skill_mds}
    assert "autoresearch" in names


def test_register_fj_builtin_skills_indexes_package_skills() -> None:
    register_fj_builtin_skills()
    assert BUILTIN_SKILLS_DIR.resolve() in [p for p, _ in SkillRoots.roots()]
    assert SkillRoots.is_builtin_directory(BUILTIN_SKILLS_DIR / "autoresearch")

    entries = SkillIndex().rebuild_if_stale()
    names = {e.name for e in entries}
    assert "autoresearch" in names
    skill = next(e for e in entries if e.name == "autoresearch")
    assert skill.source == "builtin"


def test_apply_fj_defaults_registers_skills() -> None:
    apply_fj_defaults(SootheConfig())
    assert BUILTIN_SKILLS_DIR.resolve() in [p for p, _ in SkillRoots.roots()]
