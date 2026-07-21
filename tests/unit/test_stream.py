"""Tests for AI text accumulation, progress narration, and stream_query."""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import StringIO
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from fj_ai.progress import ProgressLine
from fj_ai.stream import (
    AnswerWriter,
    _ai_text,
    _format_content,
    _status_preview,
    _truncate,
    accumulate_ai_text,
    invoke_query,
    stream_query,
)


def test_ai_text_string() -> None:
    assert _ai_text(AIMessage(content="hello")) == "hello"


def test_ai_text_blocks() -> None:
    msg = AIMessage(content=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
    assert _ai_text(msg) == "ab"


def test_ai_text_mixed_blocks_and_strings() -> None:
    msg = AIMessage(content=["pre", {"type": "text", "text": "mid"}, {"type": "image"}])
    assert _ai_text(msg) == "premid"


def test_ai_text_fallback_str(monkeypatch: pytest.MonkeyPatch) -> None:
    class WeirdMessage:
        content = 12345

    def boom(_msg: object) -> str:
        raise RuntimeError("no helper")

    # Patch inside the function's try/import path.
    import soothe_nano.utils.llm.response_text as rt

    monkeypatch.setattr(rt, "llm_response_text", boom)
    assert _ai_text(WeirdMessage()) == "12345"  # type: ignore[arg-type]


def test_truncate_and_format_content() -> None:
    assert _truncate("short") == "short"
    assert _truncate("x" * 10, limit=5) == "xxxxx…"
    assert _format_content("plain") == "plain"
    assert "[" in _format_content([{"a": 1}])
    assert _format_content(42) == "42"


def test_accumulate_chunk_deltas() -> None:
    buf = ""
    for part in ["My name is ", "Soothe", ". How can I help", " you today?"]:
        buf = accumulate_ai_text(buf, AIMessageChunk(content=part))
    assert buf == "My name is Soothe. How can I help you today?"


def test_accumulate_cumulative_snapshots() -> None:
    buf = ""
    buf = accumulate_ai_text(buf, AIMessageChunk(content="Hello"))
    buf = accumulate_ai_text(buf, AIMessageChunk(content="Hello world"))
    assert buf == "Hello world"


def test_accumulate_keeps_longer_on_shorter_replay() -> None:
    buf = accumulate_ai_text("", AIMessageChunk(content="Hello world"))
    buf = accumulate_ai_text(buf, AIMessageChunk(content="Hello"))
    assert buf == "Hello world"


def test_accumulate_empty_text_keeps_current() -> None:
    assert accumulate_ai_text("keep", AIMessageChunk(content="")) == "keep"


def test_accumulate_full_message_replaces() -> None:
    buf = accumulate_ai_text("partial", AIMessageChunk(content="partial"))
    buf = accumulate_ai_text(buf, AIMessage(content="Full final answer."))
    assert buf == "Full final answer."


def test_status_preview_prefers_latest_sentence() -> None:
    assert _status_preview("First. Second step now") == "Second step now"
    assert _status_preview("   ") == "Writing answer…"


def test_answer_writer_live_buffers_until_finish() -> None:
    out = StringIO()
    status = ProgressLine(out, enabled=False)
    writer = AnswerWriter(out, status, live=True)

    writer.set("Hello")
    writer.set("Hello world")
    assert out.getvalue() == ""
    assert writer.finish() == "Hello world"
    assert out.getvalue() == "Hello world\n"


def test_answer_writer_buffered_waits_until_finish() -> None:
    out = StringIO()
    status = ProgressLine(out, enabled=False)
    writer = AnswerWriter(out, status, live=False)

    writer.set("Hello")
    writer.set("Hello world")
    assert out.getvalue() == ""
    assert writer.finish() == "Hello world"
    assert out.getvalue() == "Hello world\n"


def test_answer_writer_reset_for_tools_drops_intermediate() -> None:
    out = StringIO()
    status = ProgressLine(out, enabled=False)
    writer = AnswerWriter(out, status, live=True)

    writer.set("Looking around")
    writer.reset_for_tools()
    writer.set("Done.")
    assert writer.finish() == "Done."
    assert out.getvalue() == "Done.\n"


def test_answer_writer_divergent_replace_keeps_latest_only() -> None:
    out = StringIO()
    status = ProgressLine(out, enabled=False)
    writer = AnswerWriter(out, status, live=True)

    writer.set("First draft")
    writer.set("Completely different")
    assert writer.finish() == "Completely different"
    assert out.getvalue() == "Completely different\n"


def test_answer_writer_live_updates_progress_preview() -> None:
    out = StringIO()
    status = ProgressLine(out, enabled=True)
    writer = AnswerWriter(out, status, live=True)
    writer.set("I'll fetch the latest stock news")
    assert "fetch the latest" in out.getvalue()
    assert writer.buf == "I'll fetch the latest stock news"
    # Progress only — not yet the committed result line.
    assert not out.getvalue().endswith("I'll fetch the latest stock news\n")


class _FakeAgent:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    async def astream(self, *_a: Any, **_k: Any) -> AsyncIterator[Any]:
        for chunk in self._chunks:
            yield chunk


def _msg_chunk(message: Any) -> tuple[tuple[()], str, tuple[Any, dict[str, Any]]]:
    return ((), "messages", (message, {}))


@pytest.mark.asyncio
async def test_stream_query_live_answer_and_custom_event() -> None:
    out = StringIO()
    err = StringIO()
    agent = _FakeAgent(
        [
            ((), "custom", {"type": "soothe.cognition.strange_loop.started"}),
            "skip-me",
            ((), "other", {}),
            _msg_chunk(AIMessageChunk(content="Hi")),
            _msg_chunk(AIMessageChunk(content="Hi there")),
        ]
    )
    result = await stream_query(
        agent,  # type: ignore[arg-type]
        "hello",
        thread_id="t1",
        show_tool_calls=True,
        live_answer=True,
        out=out,
        err=err,
        progress=ProgressLine(out, enabled=False),
    )
    assert result == "Hi there"
    assert out.getvalue() == "Hi there\n"
    assert "[event]" in err.getvalue()


@pytest.mark.asyncio
async def test_stream_query_tool_call_and_error_result() -> None:
    out = StringIO()
    err = StringIO()
    tool_msg = AIMessageChunk(
        content="",
        tool_call_chunks=[
            {
                "name": "read_file",
                "args": '{"file_path": "a.py"}',
                "id": "call_1",
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
        tool_calls=[
            {
                "name": "read_file",
                "args": {"file_path": "a.py"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    result_msg = ToolMessage(
        content="Error: unexpected keyword argument 'limit'",
        tool_call_id="call_1",
        name="read_file",
        status="error",
    )
    agent = _FakeAgent(
        [
            ((), "updates", {"__interrupt__": True}),
            _msg_chunk(tool_msg),
            _msg_chunk(result_msg),
            _msg_chunk(AIMessage(content="Recovered.")),
        ]
    )
    result = await stream_query(
        agent,  # type: ignore[arg-type]
        "read it",
        thread_id="t1",
        show_tool_calls=True,
        live_answer=True,
        out=out,
        err=err,
        progress=ProgressLine(out, enabled=False),
    )
    assert result == "Recovered."
    assert out.getvalue() == "Recovered.\n"
    stderr = err.getvalue()
    assert "[interrupted]" in stderr
    assert "[tool]" in stderr
    assert "[error]" in stderr
    assert "limit" in stderr


@pytest.mark.asyncio
async def test_stream_query_drops_intermediate_ai_narration() -> None:
    """Multi-step agent talk before tools must not appear in the final result."""
    out = StringIO()

    def tool_chunk(call_id: str) -> AIMessageChunk:
        return AIMessageChunk(
            content="",
            tool_call_chunks=[
                {
                    "name": "web_search",
                    "args": '{"query": "stock news"}',
                    "id": call_id,
                    "index": 0,
                    "type": "tool_call_chunk",
                }
            ],
            tool_calls=[
                {
                    "name": "web_search",
                    "args": {"query": "stock news"},
                    "id": call_id,
                    "type": "tool_call",
                }
            ],
        )

    agent = _FakeAgent(
        [
            _msg_chunk(AIMessage(content="I'll fetch the latest stock news.")),
            _msg_chunk(tool_chunk("call_1")),
            _msg_chunk(ToolMessage(content="headlines…", tool_call_id="call_1", name="web_search")),
            _msg_chunk(AIMessage(content="Yahoo is rate-limiting. Trying RSS.")),
            _msg_chunk(tool_chunk("call_2")),
            _msg_chunk(ToolMessage(content="rss ok", tool_call_id="call_2", name="web_search")),
            _msg_chunk(AIMessage(content="## Latest Stock Market News\n1. Futures rise")),
        ]
    )
    result = await stream_query(
        agent,  # type: ignore[arg-type]
        "latest stock news",
        thread_id="t1",
        live_answer=True,
        out=out,
        progress=ProgressLine(out, enabled=False),
    )
    assert result.startswith("## Latest Stock Market News")
    printed = out.getvalue()
    assert printed == "## Latest Stock Market News\n1. Futures rise\n"
    assert "I'll fetch" not in printed
    assert "rate-limiting" not in printed


@pytest.mark.asyncio
async def test_invoke_query_buffers_until_end() -> None:
    out = StringIO()
    agent = _FakeAgent(
        [
            _msg_chunk(AIMessageChunk(content="Final")),
            _msg_chunk(AIMessageChunk(content="Final answer")),
        ]
    )
    result = await invoke_query(
        agent,  # type: ignore[arg-type]
        "q",
        thread_id="t1",
        out=out,
        progress=ProgressLine(out, enabled=False),
    )
    assert result == "Final answer"
    assert out.getvalue() == "Final answer\n"
