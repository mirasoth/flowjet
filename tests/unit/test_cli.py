"""Unit tests for fj CLI argument parsing."""

from __future__ import annotations

import pytest

from fj_ai.argv import split_argv
from fj_ai.cli import parse_args


@pytest.mark.parametrize(
    ("argv", "options", "query"),
    [
        (["who", "is", "your", "name"], [], ["who", "is", "your", "name"]),
        (["café résumé"], [], ["café résumé"]),
        (["-v", "hello"], ["-v"], ["hello"]),
        (["--verbose", "hello", "world"], ["--verbose"], ["hello", "world"]),
        (["--", "-weird", "flag"], [], ["-weird", "flag"]),
        (["-c", "/tmp/nano.yml", "hi"], ["-c", "/tmp/nano.yml"], ["hi"]),
        (["--config=/tmp/x.yml", "q"], ["--config=/tmp/x.yml"], ["q"]),
        (["--no-stream", "ask"], ["--no-stream"], ["ask"]),
        (["-l"], ["-l"], []),
        (["--list"], ["--list"], []),
        (["-l", "-n", "5"], ["-l", "-n", "5"], []),
        (["--reset", "start", "fresh"], ["--reset"], ["start", "fresh"]),
        (["--reset"], ["--reset"], []),
        (["-lv"], ["-l", "-v"], []),
        (["-vl", "hello"], ["-v", "-l"], ["hello"]),
        (["-weird"], [], ["-weird"]),
        ([], [], []),
    ],
)
def test_split_argv(argv: list[str], options: list[str], query: list[str]) -> None:
    got_opts, got_query = split_argv(argv)
    assert got_opts == options
    assert got_query == query


def test_parse_args_joins_unicode_query() -> None:
    args = parse_args(["café", "résumé"])
    assert args.query_text == "café résumé"
    assert args.verbose is False


def test_parse_args_options() -> None:
    args = parse_args(["-v", "--thread", "t1", "-w", "/tmp", "do", "stuff"])
    assert args.verbose is True
    assert args.thread == "t1"
    assert args.workspace == "/tmp"
    assert args.query_text == "do stuff"


def test_parse_args_list_flag() -> None:
    args = parse_args(["-l"])
    assert args.list is True
    assert args.list_limit is None
    assert args.query_text == ""
    assert args.command == "query"


def test_parse_args_list_limit() -> None:
    args = parse_args(["-l", "-n", "5"])
    assert args.list is True
    assert args.list_limit == 5


def test_parse_args_reset_flag() -> None:
    args = parse_args(["--reset", "start", "fresh"])
    assert args.reset is True
    assert args.query_text == "start fresh"


def test_parse_args_reset_only() -> None:
    args = parse_args(["--reset"])
    assert args.reset is True
    assert args.query_text == ""


@pytest.mark.asyncio
async def test_run_async_list_threads(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import fj_ai.agent as agent_mod
    import fj_ai.config as config_mod
    import fj_ai.threads as threads_mod
    from fj_ai.cli import parse_args, run_async
    from fj_ai.threads import ThreadInfo

    seen: dict[str, int] = {}

    @asynccontextmanager
    async def fake_cp(_config: object):
        yield object()

    async def fake_list(_cp: object, *, limit: int = 20):
        seen["limit"] = limit
        return [
            ThreadInfo("fj-new", "2026-07-21 12:00:00", "latest question"),
            ThreadInfo("fj-old", "2026-07-20 12:00:00", "older question"),
        ]

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)
    monkeypatch.setattr(threads_mod, "list_threads", fake_list)

    assert await run_async(parse_args(["-l"])) == 0
    out = capsys.readouterr().out
    assert out.index("fj-new") < out.index("fj-old")
    assert "2026-07-21 12:00:00" in out
    assert "latest question" in out
    assert seen["limit"] == 20

    assert await run_async(parse_args(["-l", "-n", "3"])) == 0
    assert seen["limit"] == 3


@pytest.mark.asyncio
async def test_run_async_list_invalid_limit(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from types import SimpleNamespace

    import fj_ai.config as config_mod
    from fj_ai.cli import parse_args, run_async

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    assert await run_async(parse_args(["-l", "-n", "-1"])) == 2
    assert "-n must be >= 0" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_run_async_list_zero_means_all(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import fj_ai.agent as agent_mod
    import fj_ai.config as config_mod
    import fj_ai.threads as threads_mod
    from fj_ai.cli import parse_args, run_async

    seen: dict[str, int] = {}

    @asynccontextmanager
    async def fake_cp(_config: object):
        yield object()

    async def fake_list(_cp: object, *, limit: int = 20):
        seen["limit"] = limit
        return []

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)
    monkeypatch.setattr(threads_mod, "list_threads", fake_list)
    monkeypatch.setattr(threads_mod, "write_thread_list", lambda *a, **k: None)

    assert await run_async(parse_args(["-l", "-n", "0"])) == 0
    assert seen["limit"] == 0


@pytest.mark.asyncio
async def test_arg_composition_conflicts(capsys) -> None:  # type: ignore[no-untyped-def]
    from fj_ai.cli import parse_args, run_async

    cases = [
        (["-n", "5"], "-n requires -l/--list"),
        (["-n", "5", "hello"], "-n requires -l/--list"),
        (["-l", "hello"], "-l/--list does not take a query"),
        (["-l", "--reset"], "-l/--list cannot be combined with --reset"),
        (["-l", "-t", "fj-x"], "-l/--list cannot be combined with -t/--thread"),
        (["-l", "-w", "/tmp"], "-l/--list cannot be combined with -w/--workspace"),
        (["-l", "--no-stream"], "-l/--list cannot be combined with --no-stream"),
        (["--reset", "-t", "fj-x"], "--reset and -t/--thread are mutually exclusive"),
        (["--reset", "-t", "fj-x", "hi"], "--reset and -t/--thread are mutually exclusive"),
    ]
    for argv, needle in cases:
        assert await run_async(parse_args(argv)) == 2
        err = capsys.readouterr().err
        assert needle in err, (argv, err)


def test_run_pin_thread(monkeypatch, capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    import fj_ai.threads as threads_mod
    from fj_ai.cli import parse_args, run_async, run_pin_thread

    path = tmp_path / "fj_active_thread"
    monkeypatch.setattr(threads_mod, "active_thread_path", lambda: path)

    assert run_pin_thread("fj-pinned") == 0
    assert capsys.readouterr().out.strip() == "fj-pinned"
    assert path.read_text(encoding="utf-8").strip() == "fj-pinned"

    assert asyncio.run(run_async(parse_args(["-t", "fj-from-cli"]))) == 0
    assert capsys.readouterr().out.strip() == "fj-from-cli"
    assert path.read_text(encoding="utf-8").strip() == "fj-from-cli"


def test_parse_args_clustered_shorts() -> None:
    args = parse_args(["-lv"])
    assert args.list is True
    assert args.verbose is True
    assert args.query_text == ""


@pytest.mark.asyncio
async def test_run_async_default_uses_resolved_thread(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import fj_ai.agent as agent_mod
    import fj_ai.config as config_mod
    import fj_ai.stream as stream_mod
    import fj_ai.threads as threads_mod
    from fj_ai.cli import parse_args, run_async

    seen: dict[str, object] = {}

    @asynccontextmanager
    async def fake_cp(_config: object):
        yield object()

    async def fake_resolve(_cp: object, *, explicit: str | None = None, reset: bool = False) -> str:
        seen["explicit"] = explicit
        seen["reset"] = reset
        return "fj-active"

    async def fake_stream(_agent: object, query: str, *, thread_id: str, **_k: object) -> str:
        seen["query"] = query
        seen["thread_id"] = thread_id
        return "ok"

    async def fake_build(*_a: object, **_k: object) -> object:
        return object()

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)
    monkeypatch.setattr(agent_mod, "build_agent", fake_build)
    monkeypatch.setattr(threads_mod, "resolve_thread_id", fake_resolve)
    monkeypatch.setattr(stream_mod, "stream_query", fake_stream)

    assert await run_async(parse_args(["continue", "please"])) == 0
    assert seen == {
        "explicit": None,
        "reset": False,
        "query": "continue please",
        "thread_id": "fj-active",
    }


@pytest.mark.asyncio
async def test_run_async_reset_with_query_starts_new_thread(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import fj_ai.agent as agent_mod
    import fj_ai.config as config_mod
    import fj_ai.stream as stream_mod
    import fj_ai.threads as threads_mod
    from fj_ai.cli import parse_args, run_async

    seen: dict[str, object] = {}

    @asynccontextmanager
    async def fake_cp(_config: object):
        yield object()

    async def fake_resolve(_cp: object, *, explicit: str | None = None, reset: bool = False) -> str:
        seen["explicit"] = explicit
        seen["reset"] = reset
        return "fj-new"

    async def fake_stream(_agent: object, query: str, *, thread_id: str, **_k: object) -> str:
        seen["thread_id"] = thread_id
        seen["query"] = query
        return "ok"

    async def fake_build(*_a: object, **_k: object) -> object:
        return object()

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)
    monkeypatch.setattr(agent_mod, "build_agent", fake_build)
    monkeypatch.setattr(threads_mod, "resolve_thread_id", fake_resolve)
    monkeypatch.setattr(stream_mod, "stream_query", fake_stream)

    assert await run_async(parse_args(["--reset", "hello"])) == 0
    assert seen["reset"] is True
    assert seen["thread_id"] == "fj-new"
    assert seen["query"] == "hello"


def test_run_reset_only_pins_new_thread(monkeypatch, capsys, tmp_path) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    import fj_ai.threads as threads_mod
    from fj_ai.cli import parse_args, run_async, run_reset_only

    path = tmp_path / "fj_active_thread"
    monkeypatch.setattr(threads_mod, "active_thread_path", lambda: path)

    assert run_reset_only() == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("fj-")
    assert path.read_text(encoding="utf-8").strip() == out

    assert asyncio.run(run_async(parse_args(["--reset"]))) == 0
    out2 = capsys.readouterr().out.strip()
    assert out2.startswith("fj-")
    assert out2 != out


def test_parse_args_empty_query() -> None:
    args = parse_args(["-v"])
    assert args.query_text == ""


def test_parse_args_setup_command() -> None:
    args = parse_args(["setup"])
    assert args.command == "setup"
    assert args.query_text == ""


def test_main_setup_skips_asyncio(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import fj_ai.setup_cmd as setup_cmd
    from fj_ai import cli

    called: list[str] = []

    monkeypatch.setattr(cli, "configure_cli_logging", lambda: None)
    monkeypatch.setattr(setup_cmd, "run_setup", lambda _path: called.append("setup") or 0)

    def boom(*_a: object, **_k: object) -> int:
        raise AssertionError("setup must not use asyncio.run")

    monkeypatch.setattr(cli.asyncio, "run", boom)
    assert cli.main(["setup"]) == 0
    assert called == ["setup"]


def test_main_keyboard_interrupt_is_clean(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from fj_ai import cli

    def raise_ki(_argv: list[str] | None = None) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "configure_cli_logging", lambda: None)
    monkeypatch.setattr(cli, "parse_args", raise_ki)
    assert cli.main([]) == 130
    assert "interrupted" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_run_async_empty_query_prints_usage(capsys) -> None:  # type: ignore[no-untyped-def]
    from fj_ai.cli import parse_args, run_async

    assert await run_async(parse_args(["-v"])) == 2
    assert "fj — coding agent CLI" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_run_async_missing_config(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    import fj_ai.config as config_mod
    from fj_ai.cli import parse_args, run_async

    def missing(_path: object = None) -> object:
        raise FileNotFoundError("no config")

    monkeypatch.setattr(config_mod, "load_config", missing)
    code = await run_async(parse_args(["hello"]))
    assert code == 1
    assert "error: no config" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_run_async_config_load_failure(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    import fj_ai.config as config_mod
    from fj_ai.cli import parse_args, run_async

    monkeypatch.setattr(
        config_mod, "load_config", lambda _p=None: (_ for _ in ()).throw(ValueError("bad yaml"))
    )
    assert await run_async(parse_args(["hello"])) == 1
    assert "failed to load config" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_run_async_query_success_and_history(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import fj_ai.agent as agent_mod
    import fj_ai.completion.history as history_mod
    import fj_ai.config as config_mod
    import fj_ai.stream as stream_mod
    from fj_ai.cli import parse_args, run_async

    calls: list[str] = []

    @asynccontextmanager
    async def fake_cp(_config: object):
        yield object()

    async def fake_build(*_a: object, **_k: object) -> object:
        return object()

    async def fake_stream(*_a: object, **_k: object) -> str:
        calls.append("stream")
        return "ok"

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)
    monkeypatch.setattr(agent_mod, "build_agent", fake_build)
    monkeypatch.setattr(stream_mod, "stream_query", fake_stream)
    monkeypatch.setattr(history_mod, "append_history", lambda q: calls.append(f"hist:{q}"))

    async def fake_resolve(*_a: object, **_k: object) -> str:
        return "fj-test"

    import fj_ai.threads as threads_mod

    monkeypatch.setattr(threads_mod, "resolve_thread_id", fake_resolve)

    assert await run_async(parse_args(["do", "stuff"])) == 0
    assert calls == ["stream", "hist:do stuff"]


@pytest.mark.asyncio
async def test_run_async_no_stream_and_error(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import fj_ai.agent as agent_mod
    import fj_ai.config as config_mod
    import fj_ai.stream as stream_mod
    from fj_ai.cli import parse_args, run_async

    @asynccontextmanager
    async def fake_cp(_config: object):
        yield object()

    async def boom(*_a: object, **_k: object) -> str:
        raise RuntimeError("provider down")

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)

    async def fake_build(*_a: object, **_k: object) -> object:
        return object()

    async def fake_resolve(*_a: object, **_k: object) -> str:
        return "fj-test"

    import fj_ai.threads as threads_mod

    monkeypatch.setattr(agent_mod, "build_agent", fake_build)
    monkeypatch.setattr(threads_mod, "resolve_thread_id", fake_resolve)
    monkeypatch.setattr(stream_mod, "invoke_query", boom)

    args = parse_args(["--no-stream", "ask"])
    assert await run_async(args) == 1
    assert "provider down" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_run_async_keyboard_interrupt(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import fj_ai.agent as agent_mod
    import fj_ai.config as config_mod
    import fj_ai.stream as stream_mod
    from fj_ai.cli import parse_args, run_async

    @asynccontextmanager
    async def fake_cp(_config: object):
        yield object()

    async def raise_ki(*_a: object, **_k: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(config_mod, "load_config", lambda _p=None: SimpleNamespace())
    monkeypatch.setattr(agent_mod, "open_sqlite_checkpointer", fake_cp)

    async def fake_build(*_a: object, **_k: object) -> object:
        return object()

    async def fake_resolve(*_a: object, **_k: object) -> str:
        return "fj-test"

    import fj_ai.threads as threads_mod

    monkeypatch.setattr(agent_mod, "build_agent", fake_build)
    monkeypatch.setattr(threads_mod, "resolve_thread_id", fake_resolve)
    monkeypatch.setattr(stream_mod, "stream_query", raise_ki)

    assert await run_async(parse_args(["q"])) == 130
    assert "interrupted" in capsys.readouterr().err


def test_main_verbose_reconfigures_logging(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from fj_ai import cli

    seen: list[bool] = []

    def fake_logging(*, verbose: bool = False) -> None:
        seen.append(verbose)

    def fake_run(coro: object) -> int:
        # Close the coroutine to avoid "never awaited" warnings.
        if hasattr(coro, "close"):
            coro.close()  # type: ignore[union-attr]
        return 0

    monkeypatch.setattr(cli, "configure_cli_logging", fake_logging)
    monkeypatch.setattr(cli.asyncio, "run", fake_run)
    assert cli.main(["-v", "hi"]) == 0
    assert False in seen and True in seen
