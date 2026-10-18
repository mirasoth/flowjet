"""Agent construction — profiled configs turned into runtime agents."""

from __future__ import annotations

from typing import Any

from flowjet.core.backend_config import Backend, resolve_backend
from flowjet.core.modes import (
    CLI_PROFILE,
    InteractionMode,
    Surface,
    SurfaceProfile,
    require_mode,
)


class AgentFactory:
    """Build an agent for a surface profile on the selected backend.

    The backend comes from ``FLOWJET_BACKEND`` (CLI) / ``FLOWJET_SERVER_BACKEND``
    (server) unless ``backend`` is passed explicitly — see
    :mod:`flowjet.core.backend_config`.

    The server uses a dual-mode agent and supplies the interaction mode per
    request through the LangGraph ``configurable`` dict; the CLI resolves the
    mode up front and passes it to the single-mode constructor.

    ``sandbox`` is an optional soothe-nano execution backend (e.g.
    :class:`soothe_nano.sandbox.ArcBoxBackend`): when set, shell and
    workspace-file tool calls execute inside the sandbox instead of on the
    host. Both the nano and the soothe host builders accept it via their
    ``backend`` seam.
    """

    @classmethod
    def create(
        cls,
        config: Any,
        profile: SurfaceProfile = CLI_PROFILE,
        *,
        interaction_mode: InteractionMode | str | None = None,
        backend: Backend | None = None,
        sandbox: Any | None = None,
    ) -> Any:
        from flowjet.core.modes import apply_profile

        mode = require_mode(interaction_mode, profile)
        resolved = backend or resolve_backend(profile.surface)
        cfg = apply_profile(config, profile, backend=resolved)

        if resolved is Backend.SOOTHE:
            return cls.create_soothe(cfg, profile, mode, sandbox=sandbox)

        if profile.surface is Surface.SERVER:
            from soothe_nano import create_dual_mode_nano_agent

            return create_dual_mode_nano_agent(cfg, backend=sandbox)

        from soothe_nano import create_nano_agent

        return create_nano_agent(cfg, interaction_mode=mode, backend=sandbox)

    @staticmethod
    def soothe_builder() -> Any:
        """Return ``soothe.coreagent.create_soothe_agent`` (imported lazily).

        Kept as a seam so the host runtime is imported only when it is actually
        selected — the ``nano`` backend never pays for it, and tests patch this
        instead of building a real host agent.
        """
        from soothe.coreagent import create_soothe_agent

        return create_soothe_agent

    @classmethod
    def create_soothe(
        cls,
        config: Any,
        profile: SurfaceProfile = CLI_PROFILE,
        mode: str | None = None,
        *,
        sandbox: Any | None = None,
    ) -> Any:
        """Build a ``soothe`` (host runtime) agent for ``profile``'s surface.

        ``interrupt_on`` is pinned to ``{}``: the host builder otherwise injects
        HITL interrupts for mutating tools (``edit_file`` / ``write_file`` /
        ``delete`` / ``run_command``), and FlowJet has no resume path — it
        renders ``InterruptWaiting`` and stops, so any write would stall the run.
        """
        factory = cls.soothe_builder()
        if profile.surface is Surface.SERVER:
            return ModeRoutedSootheAgent(config, factory, sandbox=sandbox)
        return factory(config, interaction_mode=mode, interrupt_on={}, backend=sandbox)


class ModeRoutedSootheAgent:
    """Route one server request to the host agent built for its mode.

    soothe has no dual-mode API (nano's ``create_dual_mode_nano_agent`` has no
    host equivalent), so the server surface keeps one host agent per allowed
    mode and picks it from ``configurable["interaction_mode"]`` — an ``ask``
    request must never land on the ``agent`` graph. Agents are built lazily, so
    a worker that only serves ``ask`` never builds the ``agent`` graph.

    Only ``astream`` is proxied: that is the whole surface the nano bridge
    (``flowjet.core.bridges.nano.mapping``) drives.
    """

    def __init__(
        self,
        config: Any,
        factory: Any,
        modes: tuple[str, ...] = ("agent", "ask"),
        *,
        sandbox: Any | None = None,
    ) -> None:
        self._config = config
        self._factory = factory
        self._modes = modes
        self._sandbox = sandbox
        self._agents: dict[str, Any] = {}

    def _agent_for(self, mode: str) -> Any:
        resolved = mode if mode in self._modes else "agent"
        agent = self._agents.get(resolved)
        if agent is None:
            agent = self._factory(
                self._config,
                interaction_mode=resolved,
                interrupt_on={},
                backend=self._sandbox,
            )
            self._agents[resolved] = agent
        return agent

    async def astream(self, payload: Any, **kwargs: Any) -> Any:
        """Proxy ``astream`` to the agent built for the request's mode."""
        config = kwargs.get("config") or {}
        configurable = config.get("configurable") or {} if isinstance(config, dict) else {}
        mode = str(configurable.get("interaction_mode") or "agent")
        agent = self._agent_for(mode)
        async for chunk in agent.astream(payload, **kwargs):
            yield chunk


__all__ = ["AgentFactory", "ModeRoutedSootheAgent"]
