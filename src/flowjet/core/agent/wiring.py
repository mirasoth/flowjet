"""Server-side runtime wiring — sandbox manager, workspace resolver, backend.

Lives in core (not the HTTP layer) so the server app stays a thin adapter:
it translates :class:`~flowjet.server.config.Settings` into primitives and
delegates here. core remains server-agnostic — no imports from
``flowjet.server``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flowjet.core.backend_config import Backend, resolve_backend
from flowjet.core.bridges.nano import build_isolating_nano_backend
from flowjet.core.bridges.soothe import build_isolating_soothe_backend
from flowjet.core.modes import Surface
from flowjet.core.protocol import RuntimeBackend
from flowjet.core.sandbox.settings import SandboxSettingsLoader, ToolSandboxSettings

if TYPE_CHECKING:
    from flowjet.core.runtime.isolation.workspace import (
        SyncAwareWorkspaceResolver,
        WorkspaceResolver,
    )
    from flowjet.core.sandbox.arbox import ArcBoxToolSandboxManager
    from flowjet.core.sandbox.resolver import SandboxAwareWorkspaceResolver


class ServerRuntimeBuilder:
    """Assemble the production :class:`RuntimeBackend` for the server surface.

    Defaults to ``soothe`` (host runtime via ``ModeRoutedSootheAgent``); falls
    back to ``nano`` when ``FLOWJET_SERVER_BACKEND=nano`` is set.

    When ``sync_source`` is set, a :class:`SyncAwareWorkspaceResolver` is
    constructed and injected — enabling fsspec workspace sync. Otherwise the
    default local-only :class:`WorkspaceResolver` is used.

    When the nano.yml enables the ``sandbox:`` section, tool calls run in a
    per-workspace ArcBox microVM: a
    :class:`~flowjet.core.sandbox.arbox.ArcBoxToolSandboxManager` stages the
    workspace host↔guest and the adapters bind soothe-nano's sandbox backend
    at agent build time. The AgentRuntime isolation is unchanged (in-process
    thread pool).
    """

    @classmethod
    def build(
        cls,
        *,
        models: list[str],
        config_path: str | None,
        home: Any,
        cas_root: str | None,
        sync_source: str | None,
        sync_config_path: str | None,
        content_source: str | None,
        allow_external_workspace: bool,
        pool_settings: Any,
    ) -> RuntimeBackend:
        backend = resolve_backend(Surface.SERVER)
        sandbox_manager = cls.sandbox_manager(config_path)
        workspace_resolver = cls.workspace_resolver(
            home=home,
            cas_root=cas_root,
            sync_source=sync_source,
            sync_config_path=sync_config_path,
            content_source=content_source,
            allow_external_workspace=allow_external_workspace,
            sandbox_manager=sandbox_manager,
        )
        common: dict[str, Any] = dict(
            models=models,
            config_path=config_path,
            home=home,
            pool_settings=pool_settings,
            allow_external_workspace=allow_external_workspace,
            workspace_resolver=workspace_resolver,
            sandbox_manager=sandbox_manager,
        )
        if backend is Backend.SOOTHE:
            return build_isolating_soothe_backend(**common)
        return build_isolating_nano_backend(**common)

    @classmethod
    def sandbox_manager(cls, config_path: str | None) -> ArcBoxToolSandboxManager | None:
        """Build the ArcBox tool-sandbox manager from the nano.yml ``sandbox:`` section.

        Returns ``None`` when the sandbox is disabled (the default) — behavior
        is then identical to a host-side tools deployment. Fails loud at
        startup when the section is enabled but misconfigured (missing image)
        or the arcbox SDK is not installed.
        """
        from flowjet.core.sandbox.arbox import ArcBoxToolSandboxManager

        sandbox_settings: ToolSandboxSettings = SandboxSettingsLoader.load(config_path)
        if not sandbox_settings.enabled:
            return None
        manager = ArcBoxToolSandboxManager(sandbox_settings)
        manager.validate_runtime()
        return manager

    @classmethod
    def workspace_resolver(
        cls,
        *,
        home: Any,
        cas_root: str | None,
        sync_source: str | None,
        sync_config_path: str | None,
        content_source: str | None,
        allow_external_workspace: bool,
        sandbox_manager: ArcBoxToolSandboxManager | None = None,
    ) -> WorkspaceResolver | SyncAwareWorkspaceResolver | SandboxAwareWorkspaceResolver | None:
        """Construct the workspace resolver based on sync and sandbox settings.

        When ``sync_source`` is set, build a :class:`SyncAwareWorkspaceResolver`
        backed by an fsspec sync backend. Otherwise the resolver is the default
        local-only :class:`WorkspaceResolver`.

        When the tool sandbox is enabled, the resolver is wrapped in a
        :class:`~flowjet.core.sandbox.resolver.SandboxAwareWorkspaceResolver`
        so the host↔guest workspace staging runs inside the session lifecycle
        (guest pull before the sync checkpoint).
        """
        if sync_source and sync_source.strip():
            from flowjet.core.runtime.isolation.workspace import SyncAwareWorkspaceResolver

            inner: WorkspaceResolver | SyncAwareWorkspaceResolver = (
                SyncAwareWorkspaceResolver.from_settings(
                    home=home,
                    cas_root=cas_root,
                    sync_source=sync_source,
                    sync_config_path=sync_config_path,
                    allow_external_workspace=allow_external_workspace,
                    content_source=content_source,
                )
            )
        elif sandbox_manager is not None:
            from flowjet.core.runtime.isolation.workspace import WorkspaceResolver

            inner = WorkspaceResolver(
                home,
                allow_external_workspace=allow_external_workspace,
            )
        else:
            return None

        if sandbox_manager is None:
            return inner
        from flowjet.core.sandbox.resolver import SandboxAwareWorkspaceResolver

        return SandboxAwareWorkspaceResolver(inner, sandbox_manager)


__all__ = ["ServerRuntimeBuilder"]
