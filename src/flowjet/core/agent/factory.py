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
        checkpointer: Any | None = None,
    ) -> Any:
        from flowjet.core.modes import apply_profile

        mode = require_mode(interaction_mode, profile)
        resolved = backend or resolve_backend(profile.surface)
        cfg = apply_profile(config, profile, backend=resolved)

        if resolved is Backend.SOOTHE:
            return cls.create_soothe(cfg, profile, mode, sandbox=sandbox, checkpointer=checkpointer)

        if profile.surface is Surface.SERVER:
            from soothe_nano import create_dual_mode_nano_agent

            return create_dual_mode_nano_agent(cfg, backend=sandbox, checkpointer=checkpointer)

        from soothe_nano import create_nano_agent

        return create_nano_agent(
            cfg, interaction_mode=mode, backend=sandbox, checkpointer=checkpointer
        )

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
        checkpointer: Any | None = None,
    ) -> Any:
        """Build a ``soothe`` (host runtime) agent for ``profile``'s surface.

        ``interrupt_on`` is pinned to ``{}``: the host builder otherwise injects
        HITL interrupts for mutating tools (``edit_file`` / ``write_file`` /
        ``delete`` / ``run_command``), and FlowJet does not surface those
        approval requests as resumable pauses — only ``ask_user`` clarifications
        are resumed (via the checkpointer + ``Command(resume=...)``), so a
        mutating-tool interrupt would stall the run.

        ``checkpointer`` is attached at graph-compile time so both mode graphs
        of a server-surface agent share it (a post-hoc ``graph.checkpointer``
        assignment would only reach the default mode's lazily compiled graph).
        """
        factory = cls.soothe_builder()
        if profile.surface is Surface.SERVER:
            return ModeRoutedSootheAgent(
                config, factory, sandbox=sandbox, checkpointer=checkpointer
            )
        return factory(
            config,
            interaction_mode=mode,
            interrupt_on={},
            backend=sandbox,
            checkpointer=checkpointer,
        )


class ModeRoutedSootheAgent:
    """Route one server request to the host agent built for its mode.

    soothe has no dual-mode API (nano's ``create_dual_mode_nano_agent`` has no
    host equivalent), so the server surface keeps one host agent per allowed
    mode and picks it from ``configurable["interaction_mode"]`` — an ``ask``
    request must never land on the ``agent`` graph. Agents are built lazily, so
    a worker that only serves ``ask`` never builds the ``agent`` graph.

    Only ``astream`` and ``aget_state`` are proxied: that is the whole
    surface the nano bridge (``flowjet.core.bridges.nano.mapping``) drives
    — streaming a turn, and probing the thread snapshot for a pending
    ``ask_user`` interrupt before it.
    """

    def __init__(
        self,
        config: Any,
        factory: Any,
        modes: tuple[str, ...] = ("agent", "ask"),
        *,
        sandbox: Any | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        self._config = config
        self._factory = factory
        self._modes = modes
        self._sandbox = sandbox
        self._checkpointer = checkpointer
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
                checkpointer=self._checkpointer,
            )
            self._agents[resolved] = agent
        return agent

    def _agent_for_config(self, config: Any) -> Any:
        """Pick the mode agent for a runnable config (mirrors ``astream``)."""
        configurable: dict[str, Any] = {}
        if isinstance(config, dict):
            raw = config.get("configurable") or {}
            if isinstance(raw, dict):
                configurable = raw
        mode = str(configurable.get("interaction_mode") or "agent")
        return self._agent_for(mode)

    async def astream(self, payload: Any, **kwargs: Any) -> Any:
        """Proxy ``astream`` to the agent built for the request's mode."""
        config = kwargs.get("config") or {}
        agent = self._agent_for_config(config)
        async for chunk in agent.astream(payload, **kwargs):
            yield chunk

    async def aget_state(self, config: Any = None) -> Any:
        """Proxy ``aget_state`` to the agent built for the config's mode.

        Soft-fails to ``None`` when the mode agent cannot read graph state
        (no checkpointer), matching ``SootheNanoAgent.aget_state`` semantics
        so pending-interrupt probes degrade instead of raising.
        """
        agent = self._agent_for_config(config)
        get_state = getattr(agent, "aget_state", None)
        if not callable(get_state):
            return None
        return await get_state(config=config)


__all__ = ["AgentFactory", "ModeRoutedSootheAgent"]
