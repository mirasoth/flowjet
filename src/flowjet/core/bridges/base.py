"""Shared bridge plumbing: adapter lifecycle, agent-instance builder, factories.

``NanoAgentAdapter`` and ``SootheAgentAdapter`` share the entire per-worker
lifecycle (lazy build, sandbox binding, taint/recycle) and the same stream
mapper; they differ only in which agent constructor they are *named* for. The
backend actually used to build the agent is resolved from the environment
(``FLOWJET_SERVER_BACKEND``) inside :func:`create_server_agent_instance`, so
the shared base drives everything and the subclasses carry identity only.
"""

from __future__ import annotations

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


def create_server_agent_instance(
    config_path: str | Path | None = None,
    *,
    sandbox: Any | None = None,
) -> Any:
    """Build the server-surface agent from config on the env-selected backend.

    Server-owned invariants (workspace confinement, no ``bypass`` mode) live in
    :data:`flowjet.core.modes.SERVER_PROFILE`; they are applied by
    :class:`~flowjet.core.agent.factory.AgentFactory` rather than re-implemented
    here. ``sandbox`` is an optional soothe-nano execution backend (e.g.
    ``ArcBoxBackend``): when set, tool calls execute inside the sandbox instead
    of on the host.

    The backend (and with it the agent flavor — nano's ``DualModeCoreAgent`` or
    the host ``ModeRoutedSootheAgent``) follows ``FLOWJET_SERVER_BACKEND``.
    """
    backend = resolve_backend(Surface.SERVER)
    from flowjet.core.agent.config import FlowJetConfigLoader

    try:
        config = FlowJetConfigLoader.load(config_path, backend=backend)
    except FileNotFoundError:
        config = FlowJetConfigLoader.default(backend)
    return AgentFactory.create(config, SERVER_PROFILE, backend=backend, sandbox=sandbox)


class AgentAdapterBase:
    """Per-worker adapter lifecycle shared by the nano and soothe bridges.

    Manages one agent instance per pool worker: lazily built on first use,
    bound to a workspace's sandbox when a ``sandbox_manager`` is present
    (rebuilt when the worker switches workspaces), and recycled after a failed
    or cancelled run — cancellation can interrupt middleware cleanup and leave
    mutable graph state (for example edit-coalescing buffers) incomplete, so
    that graph is never reused for another request.
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
    ) -> None:
        self._agent = agent
        self._config_path = config_path
        self._agent_factory = agent_factory
        self._sandbox_manager = sandbox_manager
        self._agent_workspace: str | None = None
        self._active = False
        self._tainted = False
        self._generation = 1 if agent is not None else 0

    def _build(self, *, sandbox_backend: Any) -> Any:
        return create_server_agent_instance(self._config_path, sandbox=sandbox_backend)

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
            agent = self._ensure(workspace=str(req.workspace))
            # Sandbox mode: the agent's workspace is the guest root, not the
            # host path (soothe-nano sandbox semantics).
            workspace_arg = self._sandbox_manager.guest_workspace
        else:
            agent = self._ensure()
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
    ) -> IsolatingRuntimeBackend:
        """Construct the pool-backed backend with a per-worker adapter factory.

        ``sandbox_manager`` (nano.yml ``sandbox:`` section) runs tool calls in
        a per-workspace ArcBox microVM via soothe-nano's sandbox backend.
        """
        from flowjet.core.runtime.isolation import IsolatingRuntimeBackend, PoolSettings

        settings = pool_settings if pool_settings is not None else PoolSettings()

        def factory() -> Any:
            return adapter_cls(config_path=config_path, sandbox_manager=sandbox_manager)

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
