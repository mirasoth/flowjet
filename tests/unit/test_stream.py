"""Tests for AI text accumulation and live answer writing."""

from __future__ import annotations

from io import StringIO

from langchain_core.messages import AIMessage, AIMessageChunk

from fj_ai.progress import ProgressLine
from fj_ai.stream import AnswerWriter, _ai_text, accumulate_ai_text


def test_ai_text_string() -> None:
    assert _ai_text(AIMessage(content="hello")) == "hello"


def test_ai_text_blocks() -> None:
    msg = AIMessage(content=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}])
    assert _ai_text(msg) == "ab"


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


def test_accumulate_full_message_replaces() -> None:
    buf = accumulate_ai_text("partial", AIMessageChunk(content="partial"))
    buf = accumulate_ai_text(buf, AIMessage(content="Full final answer."))
    assert buf == "Full final answer."


def test_answer_writer_live_emits_deltas() -> None:
    out = StringIO()
    status = ProgressLine(out, enabled=False)
    writer = AnswerWriter(out, status, live=True)

    writer.set("Hello")
    writer.set("Hello world")
    assert out.getvalue() == "Hello world"
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


def test_answer_writer_reset_for_tools_keeps_emitted_line() -> None:
    out = StringIO()
    status = ProgressLine(out, enabled=False)
    writer = AnswerWriter(out, status, live=True)

    writer.set("Looking around")
    writer.reset_for_tools()
    writer.set("Done.")
    assert writer.finish() == "Done."
    assert out.getvalue() == "Looking around\nDone.\n"
