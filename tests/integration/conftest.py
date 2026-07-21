"""Shared fixtures for fj CLI integration tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture
def soothe_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate ``SOOTHE_HOME`` so pin/reset/lock/history never touch the real home."""
    home = tmp_path / ".soothe"
    (home / "data").mkdir(parents=True)
    (home / "config").mkdir(parents=True)
    monkeypatch.setenv("SOOTHE_HOME", str(home))
    # Avoid inheriting cloud keys that would change zero-config load_config behavior.
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    return home


@pytest.fixture
def active_thread_file(soothe_home: Path) -> Path:
    return soothe_home / "data" / "fj_active_thread"


@pytest.fixture
def stub_agent_runtime(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub agent/checkpointer/stream so query compositions never call a live model.

    Records resolve/stream/invoke/list calls for assertions.
    """
    import fj_ai.agent as agent_mod
    import fj_ai.config as config_mod
    import fj_ai.stream as stream_mod
    import fj_ai.threads as threads_mod

    seen: dict[str, Any] = {
        "resolve": None,
        "stream": None,
        "invoke": None,
        "list_limit": None,
        "workspace": None,
        "build_calls": 0,
    }

    @asynccontextmanager
    async def fake_cp(_config: object) -> Any:
        yield object()

    async def fake_resolve(
        _cp: object,
        *,
        explicit: str | None = None,
        follow: bool = False,
    ) -> str:
        seen["resolve"] = {"explicit": explicit, "follow": follow}
        if explicit:
            return explicit.strip()
        if follow:
            return "fj-active-stub"
        return "fj-new-stub"

    async def fake_list(_cp: object, *, limit: int = 20) -> list[object]:
        from fj_ai.threads import ThreadInfo

        seen["list_limit"] = limit
        return [
            ThreadInfo("fj-newer", "2026-07-21 12:00:00", "latest"),
            ThreadInfo("fj-older", "2026-07-20 12:00:00", "older"),
        ]

    async def fake_stream(_agent: object, query: str, *, thread_id: str, **_k: object) -> str:
        seen["stream"] = {"query": query, "thread_id": thread_id}
        return "ok"

    async def fake_invoke(_agent: object, query: str, *, thread_id: str) -> str:
        seen["invoke"] = {"query": query, "thread_id": thread_id}
        return "ok"

    async def fake_build(
        _config: object,
        *,
        workspace: Path | None = None,
        checkpointer: object = None,
        verbose: bool = False,
    ) -> object:
        seen["build_calls"] += 1
        seen["workspace"] = workspace
        seen["verbose"] = verbose
        return object()

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)
    monkeypatch.setattr(agent_mod, "build_agent", fake_build)
    monkeypatch.setattr(threads_mod, "resolve_thread_id", fake_resolve)
    monkeypatch.setattr(threads_mod, "list_threads", fake_list)
    monkeypatch.setattr(stream_mod, "stream_query", fake_stream)
    monkeypatch.setattr(stream_mod, "invoke_query", fake_invoke)
    # Keep real session lock (isolated via SOOTHE_HOME); no need to stub.
    return seen


@pytest.fixture
def run_fj(
    soothe_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Iterator[Any]:
    """Call ``fj_ai.cli.main(argv)`` and return ``(code, stdout, stderr)``."""
    from fj_ai import cli

    # Quiet logging setup noise across compositions.
    monkeypatch.setattr(cli, "configure_cli_logging", lambda **_k: None)

    def _run(argv: list[str]) -> tuple[int, str, str]:
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            # argparse help/version/errors raise SystemExit.
            raw = exc.code
            if raw is None:
                code = 0
            elif isinstance(raw, int):
                code = raw
            else:
                code = 1
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    yield _run


@pytest.fixture
def live_stream_runtime(
    soothe_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Stub agent wiring but run real ``stream_query`` (progress + answer path)."""
    import sys

    import fj_ai.agent as agent_mod
    import fj_ai.completion.history as history_mod
    import fj_ai.config as config_mod
    import fj_ai.threads as threads_mod
    from fj_ai.progress import ProgressLine

    # ProgressLine only paints on TTY; capsys stdout is non-interactive.
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)

    seen: dict[str, Any] = {
        "chunks": [],
        "progress_updates": 0,
        "tail_updates": 0,
    }

    class _FakeAgent:
        async def astream(self, *_a: object, **_k: object) -> Any:
            for chunk in seen["chunks"]:
                yield chunk

    @asynccontextmanager
    async def fake_cp(_config: object) -> Any:
        yield object()

    async def fake_resolve(*_a: object, **_k: object) -> str:
        return "fj-stream-stub"

    async def fake_build(*_a: object, **_k: object) -> _FakeAgent:
        return _FakeAgent()

    original_update = ProgressLine.update

    def counting_update(
        self: ProgressLine,
        message: str,
        *,
        color: str = "cyan",
        tail: bool = False,
    ) -> None:
        seen["progress_updates"] += 1
        if tail:
            seen["tail_updates"] += 1
        original_update(self, message, color=color, tail=tail)

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)
    monkeypatch.setattr(agent_mod, "build_agent", fake_build)
    monkeypatch.setattr(threads_mod, "resolve_thread_id", fake_resolve)
    monkeypatch.setattr(history_mod, "append_history", lambda _q: None)
    monkeypatch.setattr(ProgressLine, "update", counting_update)
    return seen


@pytest.fixture
def run_fjf(
    soothe_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Iterator[Any]:
    """Call ``fj_ai.cli.main_follow(argv)`` and return ``(code, stdout, stderr)``."""
    from fj_ai import cli

    monkeypatch.setattr(cli, "configure_cli_logging", lambda **_k: None)

    def _run(argv: list[str]) -> tuple[int, str, str]:
        try:
            code = cli.main_follow(argv)
        except SystemExit as exc:
            raw = exc.code
            if raw is None:
                code = 0
            elif isinstance(raw, int):
                code = raw
            else:
                code = 1
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    yield _run
