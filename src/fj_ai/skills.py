"""Register fj-packaged builtin skills with soothe-nano."""

from __future__ import annotations

from pathlib import Path

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
