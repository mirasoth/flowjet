"""Tool sandbox — run agent tool calls in a microVM via soothe-nano 2.0.

Enabled by a ``sandbox:`` section in the flowjet nano.yml. The AgentRuntime
isolation is unchanged (thread-pool workers in the server process); only the
*execution surface* moves: shell commands and workspace file operations run
inside a per-workspace sandbox through soothe-nano's
:class:`~soothe_nano.sandbox.ArcBoxBackend`, injected at agent build time.
The agent loop, LLM calls and credentials stay on the host.

The sandbox lifecycle (create/connect/kill) is owned by soothe-nano's
``ArcBoxBackend.from_config()``; flowjet only manages the **pool** — one
backend per workspace, LRU eviction, idle reaping, workspace staging, and
the disk watermark guard. No arcbox SDK symbols are imported here.

Package layout:

``settings``  — :class:`ToolSandboxSettings` and the nano.yml loader.
``arbox``     — :class:`ToolSandboxManager` (backend pool) and
                :class:`WorkspaceStager` (host↔guest file transfers).
``resolver``  — :class:`SandboxAwareWorkspaceResolver`, the workspace-resolver
                decorator that sandwiches the host↔guest staging inside the
                session lifecycle.

See ``sandbox/settings`` for the flowjet-owned ``sandbox:`` keys.
"""

from flowjet.core.sandbox.arbox import (
    SandboxDiskFullError,
    ToolSandboxManager,
    WorkspaceStager,
)
from flowjet.core.sandbox.resolver import SandboxAwareWorkspaceResolver
from flowjet.core.sandbox.settings import (
    SandboxSettingsLoader,
    ToolSandboxSettings,
)

__all__ = [
    "ToolSandboxManager",
    "SandboxAwareWorkspaceResolver",
    "SandboxDiskFullError",
    "SandboxSettingsLoader",
    "ToolSandboxSettings",
    "WorkspaceStager",
]
