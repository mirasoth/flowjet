"""ArcBox tool sandbox — run agent tool calls in a microVM via soothe-nano 2.0.

Enabled by a ``sandbox:`` section in the flowjet nano.yml. The AgentRuntime
isolation is unchanged (thread-pool workers in the server process); only the
*execution surface* moves: shell commands and workspace file operations run
inside a per-workspace ArcBox Linux microVM through soothe-nano's
:class:`~soothe_nano.sandbox.ArcBoxBackend`, injected at agent build time.
The agent loop, LLM calls and credentials stay on the host.

Package layout:

``settings``  — :class:`ToolSandboxSettings` and the nano.yml loader.
``arbox``     — :class:`ArcBoxToolSandboxManager` (VM leases) and
                :class:`WorkspaceStager` (host↔guest file transfers).
``resolver``  — :class:`SandboxAwareWorkspaceResolver`, the workspace-resolver
                decorator that sandwiches the host↔guest staging inside the
                session lifecycle.

See ``sandbox/settings`` for the flowjet-owned ``sandbox:`` keys.
"""

from flowjet.core.sandbox.arbox import (
    ArcBoxToolSandboxManager,
    SandboxDiskFullError,
    WorkspaceStager,
)
from flowjet.core.sandbox.resolver import SandboxAwareWorkspaceResolver
from flowjet.core.sandbox.settings import (
    SandboxSettingsLoader,
    ToolSandboxSettings,
)

__all__ = [
    "ArcBoxToolSandboxManager",
    "SandboxAwareWorkspaceResolver",
    "SandboxDiskFullError",
    "SandboxSettingsLoader",
    "ToolSandboxSettings",
    "WorkspaceStager",
]
