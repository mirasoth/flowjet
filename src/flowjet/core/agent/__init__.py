"""Config → agent pipeline shared by the CLI and the server.

Both surfaces used to build their agent separately, with different
constructors and contradictory security defaults. This package is the one
place where a ``SootheConfig`` is loaded, profiled and turned into an agent.
Which runtime builds that agent is decided by
:mod:`flowjet.core.backend_config` (``soothe`` host runtime or
``soothe-nano``), per surface.

Modules:

``config``     — :class:`FlowJetConfigLoader`: config path resolution and
                 backend-following ``SootheConfig`` loading.
``skills``     — :class:`BuiltinSkills`: the ``flowjet/builtin_skills`` root.
``workspace``  — :class:`Workspaces` / :class:`Checkpointers`: workspace env
                 binding and the CLI's sqlite checkpointer.
``factory``    — :class:`AgentFactory` + :class:`ModeRoutedSootheAgent`:
                 profile application and per-backend agent construction.
``wiring``     — :class:`ServerRuntimeBuilder`: server-side backend assembly
                 (sandbox manager, workspace resolver, isolating runtime).
"""

from flowjet.core.agent.config import FlowJetConfigLoader
from flowjet.core.agent.factory import AgentFactory, ModeRoutedSootheAgent
from flowjet.core.agent.skills import BUILTIN_SKILLS_DIR, FJ_CORE_SKILL_NAMES, BuiltinSkills
from flowjet.core.agent.workspace import Checkpointers, Workspaces

__all__ = [
    "BUILTIN_SKILLS_DIR",
    "FJ_CORE_SKILL_NAMES",
    "AgentFactory",
    "BuiltinSkills",
    "Checkpointers",
    "FlowJetConfigLoader",
    "ModeRoutedSootheAgent",
    "Workspaces",
]
