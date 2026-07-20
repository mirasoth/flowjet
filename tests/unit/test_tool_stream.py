"""Tests for streamed tool-call arg accumulation."""

from __future__ import annotations

from types import SimpleNamespace

from fj_ai.tool_stream import ToolCallArgAccumulator, parse_partial_args


def test_parse_partial_args_complete() -> None:
    assert parse_partial_args('{"file_path": "/tmp/a.py"}') == {"file_path": "/tmp/a.py"}


def test_parse_partial_args_incomplete() -> None:
    partial = '{"file_path": "/Users/chenxm/Workspace/fj-ai/Makefile'
    parsed = parse_partial_args(partial)
    assert parsed["file_path"].startswith("/Users/chenxm/Workspace/fj-ai/Makefile")


def test_accumulator_streams_chunked_json() -> None:
    acc = ToolCallArgAccumulator()
    chunks = [
        SimpleNamespace(
            tool_calls=[{"name": "read_file", "args": {}, "id": "call_1", "type": "tool_call"}],
            tool_call_chunks=[
                {
                    "name": "read_file",
                    "args": "",
                    "id": "call_1",
                    "index": 0,
                    "type": "tool_call_chunk",
                }
            ],
        ),
        SimpleNamespace(
            tool_calls=[
                {"name": "", "args": {"file_path": "/Users/"}, "id": "", "type": "tool_call"}
            ],
            tool_call_chunks=[
                {
                    "name": None,
                    "args": '{"file_path": "/Users/',
                    "id": "",
                    "index": 0,
                    "type": "tool_call_chunk",
                }
            ],
        ),
        SimpleNamespace(
            tool_calls=[],
            tool_call_chunks=[
                {
                    "name": None,
                    "args": 'chenxm/Workspace/fj-ai/Makefile"}',
                    "id": "",
                    "index": 0,
                    "type": "tool_call_chunk",
                }
            ],
        ),
    ]

    seen_paths: list[str] = []
    for msg in chunks:
        for _tc_id, name, args in acc.ingest_message(msg):
            assert name == "read_file"
            if "file_path" in args:
                seen_paths.append(args["file_path"])

    assert any("Makefile" in p for p in seen_paths)
    name, args = acc.args_for("call_1")
    assert name == "read_file"
    assert args.get("file_path", "").endswith("Makefile")
