"""SootheRuntimeBackend factory — IsolatingRuntimeBackend with SootheAgentAdapter.

Same ``IsolatingRuntimeBackend`` + ``ThreadPool`` as the nano bridge, with a
``SootheAgentAdapter`` factory instead of ``NanoAgentAdapter``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flowjet.core.bridges.base import IsolatingBackendBuilder
from flowjet.core.bridges.soothe.adapter import SootheAgentAdapter


def build_isolating_soothe_backend(
    *,
    models: list[str] | None = None,
    config_path: str | Path | None = None,
    home: Path | str | None = None,
    pool_settings: Any = None,
    allow_external_workspace: bool = False,
    workspace_resolver: Any = None,
    sandbox_manager: Any | None = None,
) -> Any:
    """Construct IsolatingRuntimeBackend with a SootheAgentAdapter factory."""
    return IsolatingBackendBuilder.build(
        SootheAgentAdapter,
        models=models,
        config_path=config_path,
        home=home,
        pool_settings=pool_settings,
        allow_external_workspace=allow_external_workspace,
        workspace_resolver=workspace_resolver,
        sandbox_manager=sandbox_manager,
    )


__all__ = ["build_isolating_soothe_backend"]
