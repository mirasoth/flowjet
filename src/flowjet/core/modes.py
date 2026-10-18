"""Surface profiles — the explicit home for per-surface invariants.

Before the merge, the two products carried **opposite** security defaults in
two different modules:

* ``fj_ai.agent.apply_fj_defaults`` forced ``allow_paths_outside_workspace=True``
  (a CLI runs on the user's own machine, with the user's own files) and the CLI
  defaulted to ``bypass`` mode.
* ``flowjet_server.bridges.nano.adapter`` forced it to ``False`` (a server
  hands each request an isolated workspace that tools must never escape).

Sharing one bootstrap without naming that difference would silently flip one
product's security posture. ``SurfaceProfile`` makes each invariant explicit
and per-surface, and ``require_mode`` makes ``bypass`` unreachable over HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Surface(StrEnum):
    """Which product surface is driving the runtime."""

    CLI = "cli"
    SERVER = "server"


class InteractionMode(StrEnum):
    AGENT = "agent"
    ASK = "ask"
    BYPASS = "bypass"

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any] | None) -> str:
        """Return ``agent`` or ``ask`` from request metadata (default ``agent``).

        The single parser for request-carried interaction modes — used by the
        stream mapper and the server's per-session mode gate alike. Unknown
        values fall back to ``agent``; ``bypass`` is never derived from
        request metadata (it is a CLI-only escape hatch).
        """
        raw = (metadata or {}).get("interaction_mode", cls.AGENT.value)
        return raw if raw in (cls.AGENT.value, cls.ASK.value) else cls.AGENT.value


@dataclass(frozen=True, slots=True)
class SurfaceProfile:
    """Invariants applied to a ``SootheConfig`` before an agent is built."""

    surface: Surface
    allow_paths_outside_workspace: bool
    allowed_modes: frozenset[InteractionMode]
    force_sqlite: bool = False
    seed_core_skills: bool = False
    register_builtin_skills: bool = True


CLI_PROFILE = SurfaceProfile(
    surface=Surface.CLI,
    allow_paths_outside_workspace=True,
    allowed_modes=frozenset({InteractionMode.AGENT, InteractionMode.ASK, InteractionMode.BYPASS}),
    force_sqlite=True,
    seed_core_skills=True,
    register_builtin_skills=True,
)

SERVER_PROFILE = SurfaceProfile(
    surface=Surface.SERVER,
    allow_paths_outside_workspace=False,
    allowed_modes=frozenset({InteractionMode.AGENT, InteractionMode.ASK}),
    force_sqlite=False,
    seed_core_skills=False,
    register_builtin_skills=True,
)


def require_mode(mode: InteractionMode | str | None, profile: SurfaceProfile) -> str | None:
    """Validate ``mode`` against ``profile``; return the nano-mode string.

    ``None`` means "let nano resolve the mode from config". ``bypass`` is a
    CLI-only escape hatch and is rejected for the server surface.
    """
    if mode is None:
        return None
    resolved = InteractionMode(str(mode))
    if resolved not in profile.allowed_modes:
        raise ValueError(
            f"interaction mode {resolved.value!r} is not allowed on the "
            f"{profile.surface.value} surface "
            f"(allowed: {sorted(m.value for m in profile.allowed_modes)})"
        )
    return resolved.value


def apply_profile(
    config: Any,
    profile: SurfaceProfile,
    *,
    backend: Any | None = None,
) -> Any:
    """Return a copy of ``config`` with ``profile``'s invariants applied.

    ``backend`` is a :class:`~flowjet.core.backend_config.Backend` (resolved from the
    environment when omitted). It only decides *how* the persona is owned: on
    ``soothe`` the host config's ``agent.assistant_identity`` becomes the single
    source of truth instead of FlowJet's fragment override.
    """
    from flowjet.core.agent.skills import BuiltinSkills
    from flowjet.core.backend_config import Backend, resolve_backend
    from flowjet.core.identity import (
        FLOWJET_ASSISTANT_NAME,
        configure_soothe_identity,
        install_flowjet_identity,
    )

    if profile.register_builtin_skills:
        BuiltinSkills.register()

    install_flowjet_identity()

    resolved = backend or resolve_backend(profile.surface)
    if resolved is Backend.SOOTHE:
        config = configure_soothe_identity(config)

    updates: dict[str, Any] = {}
    agent_updates: dict[str, Any] = {}

    # FlowJet is the product; nano's "Soothe" default would otherwise be the
    # assistant's name on both surfaces. An explicit ``agent.name`` wins.
    if "name" not in config.agent.model_fields_set:
        agent_updates["name"] = FLOWJET_ASSISTANT_NAME

    if profile.force_sqlite:
        durability = config.agent.protocols.durability.model_copy(
            update={"backend": "sqlite", "checkpointer": "sqlite"}
        )
        protocols = config.agent.protocols.model_copy(update={"durability": durability})
        agent_updates["protocols"] = protocols
        updates["persistence"] = config.persistence.model_copy(update={"default_backend": "sqlite"})

    if agent_updates:
        updates["agent"] = config.agent.model_copy(update=agent_updates)

    updates["security"] = config.security.model_copy(
        update={"allow_paths_outside_workspace": profile.allow_paths_outside_workspace}
    )

    if profile.seed_core_skills and config.progressive_skills.core_skills is None:
        updates["progressive_skills"] = config.progressive_skills.model_copy(
            update={"core_skills": BuiltinSkills.core_skill_names()}
        )

    return config.model_copy(update=updates)
