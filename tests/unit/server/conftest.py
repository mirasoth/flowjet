"""Shared fixtures for the server-side sandbox test suite.

The fake sandbox backend and the ``fake_backend`` factory patch were
originally defined inline in ``test_tool_sandbox.py``; they are shared here
so the concurrency/resource-consumption tests can reuse them without
duplicating ~200 lines of mock plumbing.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

# ---------------------------------------------------------------------------
# Fake sandbox backend (nano's execution surface)
# ---------------------------------------------------------------------------


class FakeArcBoxBackend:
    """Mock sandbox backend with an in-memory guest filesystem.

    Mirrors the real contract:
    - ``id``: lazily-assigned sandbox id (triggers "creation" on first access)
    - ``execute(command)``: runs a command against the in-memory tree
    - ``upload_files(files)``: writes files into the guest tree
    - ``download_files(paths)``: reads files from the guest tree
    - ``free_space_bytes()``: returns available space (configurable)
    - ``close()``: marks the backend as closed (sandbox destroyed)
    """

    _id_counter: ClassVar[int] = 0
    instances: ClassVar[list[FakeArcBoxBackend]] = []
    #: Class-level registry shared across all instances (simulates daemon state)
    registry: ClassVar[list[FakeArcBoxBackend]] = []

    def __init__(
        self,
        *,
        image: str = "",
        vcpus: int = 2,
        mem_mib: int = 2048,
        network: bool = False,
        workspace_root: str = "/workspace",
        default_timeout: int = 120,
        connect_timeout: float = 60.0,
        idle_timeout_seconds: float = 300.0,
        min_free_bytes: int = 0,
        api_url: str | None = None,
        api_key: str | None = None,
        backend_type: str = "arcbox",
    ) -> None:
        self._image = image
        self._vcpus = vcpus
        self._mem_mib = mem_mib
        self._network = network
        self._backend_type = backend_type
        self.workspace_root = workspace_root
        self.default_timeout = default_timeout
        self._connect_timeout = connect_timeout
        self._idle_timeout_seconds = idle_timeout_seconds
        self._min_free_bytes = min_free_bytes
        self._api_url = api_url
        self._api_key = api_key
        self._sandbox_id: str | None = None
        self.closed: bool = False
        self._free_space: int | None = 5 * 1024**3  # 5 GiB default
        #: In-memory guest filesystem: guest path -> bytes
        self.tree: dict[str, bytes] = {}
        #: Commands executed via execute()
        self.executed_commands: list[str] = []
        #: Files uploaded via upload_files()
        self.uploaded_files: list[str] = []
        #: Bound workspace (for os_sandbox identity mapping)
        self._bound_workspace: str | None = None
        FakeArcBoxBackend.instances.append(self)

    @property
    def backend_type(self) -> str:
        return self._backend_type

    def bind_workspace(self, host_root: str) -> None:
        """Bind the host workspace (os_sandbox identity mapping)."""
        self._bound_workspace = host_root
        # For os_sandbox, workspace_root becomes the host path.
        if self._backend_type == "os_sandbox":
            self.workspace_root = host_root

    @property
    def id(self) -> str:
        """Lazily assign a sandbox id (simulates VM creation on first use)."""
        if self._sandbox_id is None:
            FakeArcBoxBackend._id_counter += 1
            self._sandbox_id = f"sbx-{FakeArcBoxBackend._id_counter}"
            FakeArcBoxBackend.registry.append(self)
        return self._sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> SimpleNamespace:
        self.executed_commands.append(command)
        # Handle mkdir -p
        if command.startswith("mkdir -p"):
            path = command.split("mkdir -p -- ", 1)[-1].strip("'\"")
            self.tree.setdefault(path + "/.dir", b"")
            return SimpleNamespace(output="", exit_code=0)
        # Handle find ... -type f -print0
        if command.startswith("find"):
            parts = command.split()
            find_root = parts[1] if len(parts) > 1 else "/"
            prefix = find_root.rstrip("/") + "/"
            files = [p for p in self.tree if p.startswith(prefix) and not p.endswith("/.dir")]
            output = "\0".join(files)
            return SimpleNamespace(output=output, exit_code=0)
        return SimpleNamespace(output="", exit_code=0)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[SimpleNamespace]:
        responses = []
        for path, data in files:
            if not path.startswith("/"):
                responses.append(SimpleNamespace(path=path, error="invalid_path"))
                continue
            self.tree[path] = bytes(data)
            self.uploaded_files.append(path)
            responses.append(SimpleNamespace(path=path, error=None))
        return responses

    def download_files(self, paths: list[str]) -> list[SimpleNamespace]:
        responses = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(SimpleNamespace(path=path, content=None, error="invalid_path"))
                continue
            if path in self.tree:
                responses.append(SimpleNamespace(path=path, content=self.tree[path], error=None))
            else:
                responses.append(SimpleNamespace(path=path, content=None, error="not_found"))
        return responses

    def free_space_bytes(self, path: str | None = None) -> int | None:
        return self._free_space

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> type[FakeArcBoxBackend]:
    """Patch nano's create_sandbox_backend factory to return FakeArcBoxBackend.

    The factory takes a ``SandboxBackendConfig`` and dispatches to the
    registered backend. We patch it to extract the ``arcbox`` or ``os_sandbox``
    sub-config and construct a ``FakeArcBoxBackend`` from its fields.
    """
    FakeArcBoxBackend._id_counter = 0
    FakeArcBoxBackend.instances = []
    FakeArcBoxBackend.registry = []

    def _fake_create(config):
        """Fake factory: extract backend config fields and build a FakeArcBoxBackend."""
        backend_type = getattr(config, "type", None)
        if backend_type is None and isinstance(config, dict):
            backend_type = config.get("type")
        backend_type = backend_type or "arcbox"

        sub = getattr(config, backend_type, None)
        if sub is None and isinstance(config, dict):
            sub = config.get(backend_type)
        if sub is None:
            msg = f"sandbox.backend.type={backend_type!r} requires sandbox.backend.{backend_type} config"
            raise ValueError(msg)
        # Extract fields from the backend config (Pydantic model or dict)
        kwargs: dict = {"backend_type": backend_type}
        for field in (
            "image",
            "vcpus",
            "mem_mib",
            "network",
            "workspace_root",
            "default_timeout",
            "connect_timeout",
            "idle_timeout_seconds",
            "min_free_bytes",
            "api_url",
            "api_key",
        ):
            val = getattr(sub, field, None)
            if val is None and isinstance(sub, dict):
                val = sub.get(field)
            if val is not None:
                kwargs[field] = val
        return FakeArcBoxBackend(**kwargs)

    # Patch the factory function in nano's sandbox module.
    try:
        sandbox_module = __import__("soothe_nano.sandbox", fromlist=["create_sandbox_backend"])
        # The real soothe_nano.sandbox uses lazy ``__getattr__`` for
        # ``create_sandbox_backend``; ``monkeypatch.setattr`` fails on lazy
        # attributes, so set it directly on the module dict.
        try:
            monkeypatch.setattr(sandbox_module, "create_sandbox_backend", _fake_create)
        except AttributeError:
            monkeypatch.setitem(sandbox_module.__dict__, "create_sandbox_backend", _fake_create)
    except ImportError:
        # Create a minimal stub module so factory patching works even
        # without soothe-nano installed (CI without the extra).
        sandbox_module = types.ModuleType("soothe_nano.sandbox")
        sandbox_module.create_sandbox_backend = _fake_create
        monkeypatch.setitem(sys.modules, "soothe_nano.sandbox", sandbox_module)

    # Also patch SandboxBackendConfig so _spawn can construct it without nano.
    try:
        config_models = __import__("soothe_nano.config.models", fromlist=["SandboxBackendConfig"])
        if not hasattr(config_models, "SandboxBackendConfig"):
            raise ImportError("SandboxBackendConfig not in soothe_nano.config.models")
        # Keep the real SandboxBackendConfig — it works with the fake factory.
    except ImportError:
        # Stub SandboxBackendConfig as a simple namespace that preserves kwargs.
        class _StubBackendConfig:
            def __init__(self, **kwargs):
                self.type = kwargs.get("type", "arcbox")
                self.arcbox = kwargs.get("arcbox")
                self.os_sandbox = kwargs.get("os_sandbox")

        config_models = types.ModuleType("soothe_nano.config.models")
        config_models.SandboxBackendConfig = _StubBackendConfig
        # Use monkeypatch.setitem so the stub is cleaned up after the test,
        # restoring the real soothe_nano.config.models for other tests.
        if "soothe_nano.config" not in sys.modules:
            monkeypatch.setitem(
                sys.modules, "soothe_nano.config", types.ModuleType("soothe_nano.config")
            )
        monkeypatch.setitem(sys.modules, "soothe_nano.config.models", config_models)

    return FakeArcBoxBackend


@pytest.fixture()
def make_workspace() -> Callable[[Path], Path]:
    """Return a callable that builds a sample workspace tree under ``tmp_path``.

    Usage in a test::

        def test_foo(tmp_path: Path, make_workspace) -> None:
            ws = make_workspace(tmp_path)
    """

    def _make(tmp_path: Path) -> Path:
        ws = tmp_path / "ws"
        (ws / "sub").mkdir(parents=True)
        _ = (ws / "a.txt").write_text("alpha")
        _ = (ws / "sub" / "b.txt").write_text("beta")
        (ws / "__pycache__").mkdir()
        _ = (ws / "__pycache__" / "junk.pyc").write_text("junk")
        return ws

    return _make
