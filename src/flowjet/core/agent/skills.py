"""Builtin skill registration — the ``flowjet/builtin_skills`` root.

Skills belong to the distribution, not to either surface: both the CLI and
the server expose the same FlowJet skill set.
"""

from __future__ import annotations

from pathlib import Path

#: Skills ship inside the ``flowjet`` package (``src/flowjet/builtin_skills``).
BUILTIN_SKILLS_DIR = Path(__file__).resolve().parents[2] / "builtin_skills"

#: FlowJet additions on top of soothe-nano's DEFAULT_CORE_SKILL_NAMES.
FJ_CORE_SKILL_NAMES: tuple[str, ...] = ()


class BuiltinSkills:
    """Register FlowJet's builtin skill root with soothe-nano."""

    _registered = False

    @classmethod
    def register(cls) -> None:
        """Register ``flowjet/builtin_skills`` as a soothe-nano builtin skill root.

        Idempotent — safe to call from either surface and from pool worker
        threads.
        """
        if cls._registered:
            return
        if not BUILTIN_SKILLS_DIR.is_dir():
            return
        from soothe_nano.skills.builtins import SkillRoots

        SkillRoots.register(BUILTIN_SKILLS_DIR, source="builtin")
        cls._registered = True

    @staticmethod
    def core_skill_names() -> list[str]:
        """Nano default core skills plus FlowJet workflow skills."""
        from soothe_nano.skills.registry import DEFAULT_CORE_SKILL_NAMES

        return sorted(DEFAULT_CORE_SKILL_NAMES | {n.lower() for n in FJ_CORE_SKILL_NAMES})


__all__ = ["BUILTIN_SKILLS_DIR", "FJ_CORE_SKILL_NAMES", "BuiltinSkills"]
