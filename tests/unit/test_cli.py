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
