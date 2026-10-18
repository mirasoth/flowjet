"""RuntimeBackend implementations.

``direct``    — runs the agent in the caller's event loop (one-shot CLI).
``isolation`` — persistent thread pool with per-session workspaces (server).
``fake``      — echo backend with no LLM (tests / DI).

The tool-sandbox execution surface lives in :mod:`flowjet.core.sandbox` —
it is injected at agent build time, not a ``RuntimeBackend`` of its own.
"""

from __future__ import annotations

from flowjet.core.runtime.direct import DirectRuntimeBackend
from flowjet.core.runtime.fake import FakeRuntimeBackend
from flowjet.core.runtime.isolation import (
    AgentAdapter,
    FakeAgentAdapter,
    InteractionModeGate,
    IsolatedRunRequest,
    IsolatingRuntimeBackend,
    IsolationError,
    PoolMetrics,
    PoolSettings,
    SessionAdmission,
    SyncAwareWorkspaceResolver,
    ThreadPool,
    WorkspaceResolver,
)

__all__ = [
    "AgentAdapter",
    "DirectRuntimeBackend",
    "FakeAgentAdapter",
    "FakeRuntimeBackend",
    "IsolatedRunRequest",
    "IsolatingRuntimeBackend",
    "InteractionModeGate",
    "IsolationError",
    "PoolMetrics",
    "PoolSettings",
    "SessionAdmission",
    "SyncAwareWorkspaceResolver",
    "ThreadPool",
    "WorkspaceResolver",
]
