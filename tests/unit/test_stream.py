"""Tests for AI text accumulation across stream chunks."""

from __future__ import annotations

from langchain_core.messages import AIMessage, AIMessageChunk

from fj_ai.stream import _ai_text, accumulate_ai_text


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
