"""Agent Runtime Protocol — typed events and RuntimeBackend.

Surface-agnostic: neither ``flowjet.cli`` nor ``flowjet.server`` is imported
here, and both import from here.

Package map:

``events`` / ``protocol`` — the event vocabulary and the RuntimeBackend protocol.
``modes``                 — per-surface security invariants and interaction modes.
``backend_config``        — which runtime (soothe / nano) builds the agent.
``runtime``               — RuntimeBackend implementations (direct / isolation / fake).
``bridges``               — soothe-nano / soothe host adapters and the stream mapper.
``agent``                 — config → agent pipeline and server wiring.
``sandbox``               — ArcBox microVM tool-sandbox (execution surface).
``streaming``             — tool-arg accumulation and presentation helpers.
``identity``              — FlowJet persona override over soothe-nano.
"""

from __future__ import annotations

from flowjet.core.backend_config import (
    CLI_BACKEND_ENV,
    SERVER_BACKEND_ENV,
    Backend,
    resolve_backend,
)
from flowjet.core.events import (
    InterruptWaiting,
    ModelInfo,
    OutputTextDelta,
    Progress,
    RunCompleted,
    RunFailed,
    RunRequest,
    RunStarted,
    RuntimeEvent,
    ToolCompleted,
    ToolStarted,
    UsageInfo,
)
from flowjet.core.modes import (
    CLI_PROFILE,
    SERVER_PROFILE,
    InteractionMode,
    Surface,
    SurfaceProfile,
)
from flowjet.core.protocol import RuntimeBackend
from flowjet.core.runtime.fake import FakeRuntimeBackend

__all__ = [
    "CLI_BACKEND_ENV",
    "CLI_PROFILE",
    "SERVER_BACKEND_ENV",
    "SERVER_PROFILE",
    "Backend",
    "FakeRuntimeBackend",
    "InteractionMode",
    "InterruptWaiting",
    "ModelInfo",
    "OutputTextDelta",
    "Progress",
    "RunCompleted",
    "RunFailed",
    "RunRequest",
    "RunStarted",
    "RuntimeBackend",
    "RuntimeEvent",
    "Surface",
    "SurfaceProfile",
    "ToolCompleted",
    "ToolStarted",
    "UsageInfo",
    "resolve_backend",
]
