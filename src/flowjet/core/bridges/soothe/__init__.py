"""soothe (host runtime) → Agent Runtime Protocol bridge."""

from flowjet.core.bridges.soothe.adapter import (
    SootheAgentAdapter,
    create_soothe_agent_instance,
)
from flowjet.core.bridges.soothe.backend import build_isolating_soothe_backend

__all__ = [
    "SootheAgentAdapter",
    "build_isolating_soothe_backend",
    "create_soothe_agent_instance",
]
