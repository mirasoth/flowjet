"""SootheAgentAdapter — soothe host runtime runner for the isolation ThreadPool.

Mirrors :class:`~flowjet.core.bridges.nano.adapter.NanoAgentAdapter`: same
``AgentAdapterBase`` lifecycle, same stream mapping via
:func:`~flowjet.core.bridges.nano.mapping.iter_nano_runtime_events`. The
stream mapping is shared because the host runtime emits the same chunk
vocabulary as nano (``messages``, ``updates``, ``custom``) plus host-specific
custom types that the mapper already handles
(``soothe.stream.tool_call.update``, host middleware phase events, etc.).

The host agent is a :class:`~flowjet.core.agent.factory.ModeRoutedSootheAgent`
that lazily builds one graph per interaction mode (``agent`` / ``ask``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from flowjet.core.bridges.base import AgentAdapterBase, create_server_agent_instance

if TYPE_CHECKING:
    from flowjet.core.sandbox.arbox import ArcBoxToolSandboxManager

#: Historical name — identical to the shared server instance builder; the
#: backend flavor follows ``FLOWJET_SERVER_BACKEND``.
create_soothe_agent_instance = create_server_agent_instance


class SootheAgentAdapter(AgentAdapterBase):
    """AgentAdapter wrapping a host soothe agent (one instance per pool worker).

    The adapter manages the same taint/recycle lifecycle as
    ``NanoAgentAdapter``: if a run fails or is cancelled, the agent is
    discarded so mutable graph state never leaks into the next request.
    """

    label = "SootheAgentAdapter"


def soothe_adapter_factory(
    *,
    config_path: str | None = None,
    sandbox_manager: ArcBoxToolSandboxManager | None = None,
):
    """Return a zero-arg factory suitable for ThreadPool / IsolatingRuntimeBackend."""

    def factory() -> SootheAgentAdapter:
        return SootheAgentAdapter(config_path=config_path, sandbox_manager=sandbox_manager)

    return factory


__all__ = ["SootheAgentAdapter", "create_soothe_agent_instance", "soothe_adapter_factory"]
