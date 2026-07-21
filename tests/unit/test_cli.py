"""Unit tests for fj CLI argument parsing."""

from __future__ import annotations

import pytest

from fj_ai.cli import parse_args, split_argv


@pytest.mark.parametrize(
    ("argv", "options", "query"),
    [
        (["who", "is", "your", "name"], [], ["who", "is", "your", "name"]),
        (["修改这个文件。"], [], ["修改这个文件。"]),
        (["-v", "hello"], ["-v"], ["hello"]),
        (["--verbose", "hello", "world"], ["--verbose"], ["hello", "world"]),
        (["--", "-weird", "flag"], [], ["-weird", "flag"]),
        (["-c", "/tmp/nano.yml", "hi"], ["-c", "/tmp/nano.yml"], ["hi"]),
        (["--config=/tmp/x.yml", "q"], ["--config=/tmp/x.yml"], ["q"]),
        (["--no-stream", "ask"], ["--no-stream"], ["ask"]),
        ([], [], []),
    ],
)
def test_split_argv(argv: list[str], options: list[str], query: list[str]) -> None:
    got_opts, got_query = split_argv(argv)
    assert got_opts == options
    assert got_query == query


def test_parse_args_joins_unicode_query() -> None:
    args = parse_args(["修改这个文件。", "并解释原因"])
    assert args.query_text == "修改这个文件。 并解释原因"
    assert args.verbose is False


def test_parse_args_options() -> None:
    args = parse_args(["-v", "--thread", "t1", "-w", "/tmp", "do", "stuff"])
    assert args.verbose is True
    assert args.thread == "t1"
    assert args.workspace == "/tmp"
    assert args.query_text == "do stuff"


def test_parse_args_empty_query() -> None:
    args = parse_args(["-v"])
    assert args.query_text == ""


def test_parse_args_setup_command() -> None:
    args = parse_args(["setup"])
    assert args.command == "setup"
    assert args.query_text == ""


def test_main_setup_skips_asyncio(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from fj_ai import cli

    called: list[str] = []

    monkeypatch.setattr(cli, "configure_cli_logging", lambda: None)
    monkeypatch.setattr(cli, "run_setup", lambda _path: called.append("setup") or 0)

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
