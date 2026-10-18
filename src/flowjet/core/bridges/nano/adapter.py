"""NanoAgentAdapter — soothe-nano runner for the isolation ThreadPool.

The full per-worker lifecycle (lazy build, sandbox binding, taint/recycle)
lives in :class:`~flowjet.core.bridges.base.AgentAdapterBase`; this subclass
carries the nano identity. The agent flavor itself follows
``FLOWJET_SERVER_BACKEND`` — see :func:`create_server_agent_instance`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flowjet.core.bridges.base import AgentAdapterBase, create_server_agent_instance

if TYPE_CHECKING:
    from flowjet.core.sandbox.arbox import ArcBoxToolSandboxManager

#: Historical name — identical to the shared server instance builder; the
#: backend flavor follows ``FLOWJET_SERVER_BACKEND``.
create_nano_agent_instance = create_server_agent_instance


class NanoAgentAdapter(AgentAdapterBase):
    """AgentAdapter wrapping DualModeCoreAgent (one instance per pool worker).

    With a ``sandbox_manager`` (nano.yml ``sandbox:`` section), tool calls run
    in a per-workspace ArcBox microVM: the agent is bound to the workspace's
    sandbox at build time and rebuilt when the worker switches workspaces.
    """

    label = "NanoAgentAdapter"


def nano_adapter_factory(
    *,
    config_path: str | None = None,
    sandbox_manager: ArcBoxToolSandboxManager | None = None,
):
    """Return a zero-arg factory suitable for ThreadPool / IsolatingRuntimeBackend."""

    def factory() -> NanoAgentAdapter:
        return NanoAgentAdapter(config_path=config_path, sandbox_manager=sandbox_manager)

    return factory


__all__ = ["NanoAgentAdapter", "create_nano_agent_instance", "nano_adapter_factory"]
