"""Shared bridge plumbing: adapter lifecycle, agent-instance builder, factories.

``NanoAgentAdapter`` and ``SootheAgentAdapter`` share the entire per-worker
lifecycle (lazy build, sandbox binding, taint/recycle) and the same stream
mapper; they differ only in which agent constructor they are *named* for. The
backend actually used to build the agent is resolved from the environment
(``FLOWJET_SERVER_BACKEND``) inside :func:`create_server_agent_instance`, so
the shared base drives everything and the subclasses carry identity only.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from flowjet.core.agent.factory import AgentFactory
from flowjet.core.backend_config import resolve_backend
from flowjet.core.bridges.nano.mapping import iter_nano_runtime_events
from flowjet.core.events import RunCompleted, RunFailed, RuntimeEvent
from flowjet.core.modes import SERVER_PROFILE, InteractionMode, Surface
from flowjet.core.runtime.isolation.request import IsolatedRunRequest

if TYPE_CHECKING:
    from flowjet.core.runtime.isolation.backend import IsolatingRuntimeBackend
    from flowjet.core.sandbox.arbox import ArcBoxToolSandboxManager

logger = logging.getLogger(__name__)


def create_server_agent_instance(
    config_path: str | Path | None = None,
    *,
    sandbox: Any | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Build the server-surface agent from config on the env-selected backend.

    Server-owned invariants (workspace confinement, no ``bypass`` mode) live in
    :data:`flowjet.core.modes.SERVER_PROFILE`; they are applied by
    :class:`~flowjet.core.agent.factory.AgentFactory` rather than re-implemented
    here. ``sandbox`` is an optional soothe-nano execution backend (e.g.
    ``ArcBoxBackend``): when set, tool calls execute inside the sandbox instead
    of on the host. ``checkpointer`` persists thread state across turns (and
    across pool workers / restarts when backed by a shared store) and is what
    makes ``ask_user`` pauses resumable.

    The backend (and with it the agent flavor — nano's ``DualModeCoreAgent`` or
    the host ``ModeRoutedSootheAgent``) follows ``FLOWJET_SERVER_BACKEND``.
    """
    backend = resolve_backend(Surface.SERVER)
    from flowjet.core.agent.config import FlowJetConfigLoader

    try:
        config = FlowJetConfigLoader.load(config_path, backend=backend)
    except FileNotFoundError:
        config = FlowJetConfigLoader.default(backend)
    return AgentFactory.create(
        config, SERVER_PROFILE, backend=backend, sandbox=sandbox, checkpointer=checkpointer
    )


class AgentAdapterBase:
    """Per-worker adapter lifecycle shared by the nano and soothe bridges.

    Manages one agent instance per pool worker: lazily built on first use,
    bound to a workspace's sandbox when a ``sandbox_manager`` is present
    (rebuilt when the worker switches workspaces), and recycled after a failed
    or cancelled run — cancellation can interrupt middleware cleanup and leave
    mutable graph state (for example edit-coalescing buffers) incomplete, so
    that graph is never reused for another request.

    Thread state, by contrast, is *not* worker-local: when
    ``checkpointer_policy`` is enabled the adapter opens one checkpointer on
    the worker's event loop (aiosqlite connections are loop-bound, so it cannot
    be shared across workers) pointing at the shared store resolved from the
    config. The checkpointer outlives agent rebuilds — taint recycling discards
    the graph, never the conversation.
    """

    #: Display name for concurrency-error messages (subclass identity).
    label: ClassVar[str] = "AgentAdapter"

    def __init__(
        self,
        agent: Any | None = None,
        *,
        config_path: str | Path | None = None,
        agent_factory: Any | None = None,
        sandbox_manager: ArcBoxToolSandboxManager | None = None,
        checkpointer_policy: str | None = "off",
    ) -> None:
        self._agent = agent
        self._config_path = config_path
        self._agent_factory = agent_factory
        self._sandbox_manager = sandbox_manager
        self._checkpointer_policy = str(checkpointer_policy or "off").strip().lower()
        self._checkpointer: Any | None = None
        self._checkpointer_cm: Any | None = None
        self._checkpointer_failed = False
        self._agent_workspace: str | None = None
        self._active = False
        self._tainted = False
        self._generation = 1 if agent is not None else 0

    def _build(self, *, sandbox_backend: Any) -> Any:
        return create_server_agent_instance(
            self._config_path,
            sandbox=sandbox_backend,
            checkpointer=self._checkpointer,
        )

    async def _ensure_checkpointer(self) -> Any | None:
        """Open the shared checkpointer on this worker's event loop (once).

        Failure is sticky and non-fatal: the server keeps serving turns without
        cross-turn memory (the pre-checkpointer behavior) instead of dying.
        """
        from flowjet.core.agent.workspace import checkpointer_policy_enabled

        if not checkpointer_policy_enabled(self._checkpointer_policy):
            return None
        if self._checkpointer is not None or self._checkpointer_failed:
            return self._checkpointer
        from flowjet.core.agent.config import FlowJetConfigLoader
        from flowjet.core.agent.workspace import Checkpointers

        backend = resolve_backend(Surface.SERVER)
        try:
            config = FlowJetConfigLoader.load(self._config_path, backend=backend)
        except FileNotFoundError:
            config = FlowJetConfigLoader.default(backend)
        try:
            cm = Checkpointers.open(config)
            checkpointer = await cm.__aenter__()
        except Exception:  # noqa: BLE001 - persistence is degraded, not fatal
            self._checkpointer_failed = True
            logger.warning(
                "%s: server checkpointer unavailable; turns will not persist thread state",
                self.label,
                exc_info=True,
            )
            return None
        self._checkpointer_cm = cm
        self._checkpointer = checkpointer
        return checkpointer

    async def _ensure_agent(self, *, workspace: str | None = None) -> Any:
        """Async ensure: open the checkpointer before a config-driven build."""
        needs_build = self._agent is None or (
            self._sandbox_manager is not None and self._agent_workspace != workspace
        )
        if needs_build and self._agent_factory is None:
            await self._ensure_checkpointer()
        return self._ensure(workspace=workspace)

    def _ensure(self, *, workspace: str | None = None) -> Any:
        if self._agent is not None:
            if self._sandbox_manager is None or self._agent_workspace == workspace:
                return self._agent
            # The sandbox backend is bound at build time — a workspace
            # switch needs a fresh agent bound to the new sandbox.
            self._agent = None
        if self._agent_factory is not None:
            self._agent = self._agent_factory()
        else:
            sandbox_backend = None
            if self._sandbox_manager is not None and workspace is not None:
                sandbox_backend = self._sandbox_manager.backend_for(workspace)
            self._agent = self._build(sandbox_backend=sandbox_backend)
        self._agent_workspace = workspace
        self._generation += 1
        return self._agent

    async def astream(self, req: IsolatedRunRequest) -> AsyncIterator[RuntimeEvent]:
        if self._active:
            raise RuntimeError(f"{self.label} cannot execute concurrent requests")
        self._active = True
        completed = False
        if self._sandbox_manager is not None:
            agent = await self._ensure_agent(workspace=str(req.workspace))
            # Sandbox mode: the agent's workspace is the guest root, not the
            # host path (soothe-nano sandbox semantics).
            workspace_arg = self._sandbox_manager.guest_workspace
        else:
            agent = await self._ensure_agent()
            workspace_arg = str(req.workspace)
        mode = InteractionMode.from_metadata(req.metadata)
        try:
            async for event in iter_nano_runtime_events(
                agent,
                run_id=req.run_id,
                model=req.model,
                session=req.session,
                input_text=req.input_text,
                workspace=workspace_arg,
                thread_id=req.effective_thread_id(),
                interaction_mode=mode,
                resume_value=req.resume_value,
            ):
                if isinstance(event, RunFailed):
                    self._tainted = True
                elif isinstance(event, RunCompleted):
                    completed = True
                yield event
        finally:
            if not completed:
                self._tainted = True
            self._active = False

    def prepare_for_request(self) -> None:
        """Finalize one turn and recycle an agent after abnormal termination."""
        if self._active:
            raise RuntimeError(f"cannot prepare an active {self.label}")
        if self._tainted:
            self._agent = None
            self._agent_workspace = None
            self._tainted = False

    async def cleanup(self) -> None:
        self._agent = None
        self._agent_workspace = None
        self._tainted = False
        self._active = False
        cm, self._checkpointer_cm = self._checkpointer_cm, None
        self._checkpointer = None
        if cm is not None:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                logger.debug("%s: checkpointer close failed", self.label, exc_info=True)

    @property
    def generation(self) -> int:
        """Number of agent instances materialized by this adapter."""
        return self._generation


class IsolatingBackendBuilder:
    """Assemble an :class:`IsolatingRuntimeBackend` for a bridge adapter class."""

    @staticmethod
    def build(
        adapter_cls: type,
        *,
        models: list[str] | None = None,
        config_path: str | Path | None = None,
        home: Path | str | None = None,
        pool_settings: Any = None,
        allow_external_workspace: bool = False,
        workspace_resolver: Any = None,
        sandbox_manager: Any | None = None,
        checkpointer_policy: str | None = "off",
    ) -> IsolatingRuntimeBackend:
        """Construct the pool-backed backend with a per-worker adapter factory.

        ``sandbox_manager`` (nano.yml ``sandbox:`` section) runs tool calls in
        a per-workspace ArcBox microVM via soothe-nano's sandbox backend.
        ``checkpointer_policy`` ("auto" from the server wiring, "off" by
        default) makes each worker's adapter open the shared thread-state
        checkpointer.
        """
        from flowjet.core.runtime.isolation import IsolatingRuntimeBackend, PoolSettings

        settings = pool_settings if pool_settings is not None else PoolSettings()

        def factory() -> Any:
            return adapter_cls(
                config_path=config_path,
                sandbox_manager=sandbox_manager,
                checkpointer_policy=checkpointer_policy,
            )

        return IsolatingRuntimeBackend(
            models=models,
            adapter_factory=factory,
            pool_settings=settings,
            home=home,
            allow_external_workspace=allow_external_workspace,
            workspace_resolver=workspace_resolver,
        )


__all__ = [
    "AgentAdapterBase",
    "IsolatingBackendBuilder",
    "create_server_agent_instance",
]
