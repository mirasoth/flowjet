"""Register fj-packaged builtin skills with soothe-nano."""

from __future__ import annotations

from pathlib import Path

_REGISTERED = False

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "builtin_skills"


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
