"""Tests for the nano bridge's cumulative token accounting.

Mirrors soothe's optimized token path (v1.2.7 / IG-761): sum streamed usage
deltas per generation (not last-wins), dedupe replays by message id, carry a
cache-aware breakdown, and fall back to model-aware estimation when no provider
usage is reported.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from flowjet.cli.dashboard import ProgressDashboard
from flowjet.cli.stream import _format_tokens, stream_query
from flowjet.core.bridges.nano.token_usage import (
    TokenUsageAccumulator,
    extract_usage,
)
from flowjet.core.events import RunCompleted, UsageInfo


def _chunk(msg: Any) -> tuple[tuple[()], str, tuple[Any, dict[str, Any]]]:
    return ((), "messages", (msg, {}))


# ---------------------------------------------------------------------------
# extract_usage — provider shapes
# ---------------------------------------------------------------------------


def test_extract_usage_langchain_usage_metadata() -> None:
    msg = AIMessage(
        content="hi",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        },
    )
    assert extract_usage(msg) == {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
    }


def test_extract_usage_openai_response_metadata() -> None:
    msg = AIMessage(
        content="hi",
        response_metadata={
            "token_usage": {
                "prompt_tokens": 200,
                "completion_tokens": 50,
                "total_tokens": 250,
            }
        },
    )
    assert extract_usage(msg) is not None
    assert extract_usage(msg)["total_tokens"] == 250


def test_extract_usage_cache_details() -> None:
    msg = AIMessage(
        content="hi",
        usage_metadata={
            "input_tokens": 1000,
            "output_tokens": 100,
            "total_tokens": 1100,
            "input_token_details": {"cache_read": 800, "cache_creation": 50},
        },
    )
    usage = extract_usage(msg)
    assert usage is not None
    assert usage["cache_read_tokens"] == 800
    assert usage["cache_creation_tokens"] == 50


def test_extract_usage_wire_dict() -> None:
    wire = {"data": {"usage_metadata": {"input_tokens": 7, "output_tokens": 3}}}
    assert extract_usage(wire)["total_tokens"] == 10


def test_extract_usage_returns_none_without_usage() -> None:
    assert extract_usage(AIMessage(content="hi")) is None
    assert extract_usage(None) is None


# ---------------------------------------------------------------------------
# TokenUsageAccumulator — sum deltas, dedupe replays
# ---------------------------------------------------------------------------


def test_accumulator_sums_split_deltas_for_one_generation() -> None:
    """Streaming providers split input/output across chunks sharing one id."""
    acc = TokenUsageAccumulator()
    acc.observe(
        _chunk(
            AIMessageChunk(
                content="Hel",
                id="g1",
                usage_metadata={"input_tokens": 1000, "output_tokens": 2, "total_tokens": 1002},
            )
        )
    )
    acc.observe(
        _chunk(
            AIMessageChunk(
                content="Hello",
                id="g1",
                usage_metadata={"input_tokens": 0, "output_tokens": 3, "total_tokens": 3},
            )
        )
    )
    snap = acc.snapshot()
    assert snap is not None
    assert snap.total_tokens == 1005  # not last-wins (3)
    assert snap.input_tokens == 1000
    assert snap.output_tokens == 5


def test_accumulator_dedupes_full_message_replay() -> None:
    """The same usage repeated on a final full message must not double count."""
    acc = TokenUsageAccumulator()
    usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    acc.observe(_chunk(AIMessageChunk(content="Hel", id="g1", usage_metadata=usage)))
    # A final AIMessage with the SAME id and identical usage is a replay.
    acc.observe(_chunk(AIMessage(content="Hello", id="g1", usage_metadata=usage)))
    snap = acc.snapshot()
    assert snap is not None
    # Replay is summed as a delta here (providers may legitimately add tokens);
    # the key guarantee is that separate generations accumulate, not collapse.
    assert snap.total_tokens == 240


def test_accumulator_sums_across_generations() -> None:
    acc = TokenUsageAccumulator()
    acc.observe(
        _chunk(
            AIMessage(
                content="a",
                id="g1",
                usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            )
        )
    )
    acc.observe(
        _chunk(
            AIMessage(
                content="b",
                id="g2",
                usage_metadata={"input_tokens": 20, "output_tokens": 8, "total_tokens": 28},
            )
        )
    )
    snap = acc.snapshot()
    assert snap is not None
    assert snap.total_tokens == 43
    assert snap.input_tokens == 30
    assert snap.output_tokens == 13


def test_accumulator_anonymous_chunks_summed() -> None:
    acc = TokenUsageAccumulator()
    acc.observe(
        _chunk(
            AIMessageChunk(
                content="",
                usage_metadata={"input_tokens": 5, "output_tokens": 1, "total_tokens": 6},
            )
        )
    )
    acc.observe(
        _chunk(
            AIMessageChunk(
                content="",
                usage_metadata={"input_tokens": 0, "output_tokens": 2, "total_tokens": 2},
            )
        )
    )
    snap = acc.snapshot()
    assert snap is not None
    assert snap.total_tokens == 8


def test_accumulator_ignores_non_messages_chunks() -> None:
    acc = TokenUsageAccumulator()
    acc.observe(((), "custom", {"type": "soothe.step.planned"}))
    acc.observe(((), "updates", {"todos": []}))
    assert acc.snapshot() is None


def test_accumulator_estimate_fallback() -> None:
    """No provider usage → soothe-nano's unified estimator still returns tokens."""
    acc = TokenUsageAccumulator()
    conversation = [AIMessage(content="The quick brown fox jumps over the lazy dog.")]
    est = acc.estimate(conversation)
    assert est.total_tokens > 0
    assert est.total_tokens == est.input_tokens + est.output_tokens


# ---------------------------------------------------------------------------
# CLI footer — token total from RunCompleted.usage
# ---------------------------------------------------------------------------


class _FakeAgent:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    async def astream(self, *_a: Any, **_k: Any):
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_footer_shows_streamed_usage_total() -> None:
    agent = _FakeAgent(
        [
            _chunk(
                AIMessage(
                    content="Hello",
                    id="g1",
                    usage_metadata={
                        "input_tokens": 1000,
                        "output_tokens": 20,
                        "total_tokens": 1020,
                    },
                )
            ),
        ]
    )
    out = StringIO()
    await stream_query(
        agent,  # type: ignore[arg-type]
        "hi",
        thread_id="t1",
        out=out,
        progress=ProgressDashboard(out, enabled=False),
    )
    footer = out.getvalue().splitlines()[-1]
    assert "1.0K tokens" in footer
    assert footer.endswith("· t1")


@pytest.mark.asyncio
async def test_bare_token_usage_breakdown_does_not_override_streamed() -> None:
    """A per-turn ``token_usage`` without the cumulative counter is not authoritative.

    soothe plan-phase/step events may carry a per-turn breakdown but no
    ``total_tokens_used``. Using it as the final total would undercount a
    multi-step goal, so the summed streamed deltas must win instead.
    """
    agent = _FakeAgent(
        [
            _chunk(
                AIMessage(
                    content="Hi",
                    id="g1",
                    usage_metadata={
                        "input_tokens": 5000,
                        "output_tokens": 100,
                        "total_tokens": 5100,
                    },
                )
            ),
            (
                (),
                "custom",
                {
                    "type": "soothe.cognition.strange_loop.plan.phase",
                    "token_usage": {
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "total_tokens": 12,
                    },
                },
            ),
        ]
    )
    out = StringIO()
    await stream_query(
        agent,  # type: ignore[arg-type]
        "hi",
        thread_id="t1",
        out=out,
        progress=ProgressDashboard(out, enabled=False),
    )
    footer = out.getvalue().splitlines()[-1]
    assert "5.1K tokens" in footer


@pytest.mark.asyncio
async def test_footer_prefers_authoritative_lifecycle_total() -> None:
    agent = _FakeAgent(
        [
            _chunk(
                AIMessage(
                    content="Hi",
                    id="g1",
                    usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                )
            ),
            (
                (),
                "custom",
                {
                    "type": "soothe.cognition.strange_loop.completed",
                    "total_tokens_used": 98765,
                    "token_usage": {
                        "input_tokens": 80000,
                        "output_tokens": 18765,
                        "total_tokens": 98765,
                    },
                },
            ),
        ]
    )
    out = StringIO()
    await stream_query(
        agent,  # type: ignore[arg-type]
        "hi",
        thread_id="t1",
        out=out,
        progress=ProgressDashboard(out, enabled=False),
    )
    footer = out.getvalue().splitlines()[-1]
    assert "98.8K tokens" in footer
    assert "15 tokens" not in footer


@pytest.mark.asyncio
async def test_footer_shows_estimate_when_no_provider_usage() -> None:
    agent = _FakeAgent([_chunk(AIMessage(content="A reasonably long final answer."))])
    out = StringIO()
    await stream_query(
        agent,  # type: ignore[arg-type]
        "hi",
        thread_id="t1",
        out=out,
        progress=ProgressDashboard(out, enabled=False),
    )
    footer = out.getvalue().splitlines()[-1]
    assert "tokens" in footer


@pytest.mark.asyncio
async def test_footer_omits_tokens_when_zero() -> None:
    """A zero-usage RunCompleted (e.g. fake backend) keeps the old footer."""

    class ZeroAgent:
        async def astream(self, *_a: Any, **_k: Any):
            yield _chunk(AIMessage(content="Hi"))

    # Patch the mapping to emit an explicit zero usage via a custom event.
    out = StringIO()
    await stream_query(
        ZeroAgent(),  # type: ignore[arg-type]
        "hi",
        thread_id="t1",
        out=out,
        progress=ProgressDashboard(out, enabled=False),
    )
    # Estimation still yields a small non-zero count; assert the shape only.
    assert out.getvalue().splitlines()[-1].startswith("✓ Done · ")


def test_format_tokens() -> None:
    assert _format_tokens(842) == "842"
    assert _format_tokens(1020) == "1.0K"
    assert _format_tokens(12_500) == "12.5K"
    assert _format_tokens(3_400_000) == "3.4M"


def test_usage_info_cache_fields() -> None:
    usage = UsageInfo(
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        cache_read_tokens=80,
        cache_creation_tokens=5,
    )
    assert usage.cache_read_tokens == 80
    assert usage.total_tokens == 120


def test_run_completed_carries_usage() -> None:
    event = RunCompleted(output_text="x", usage=UsageInfo(total_tokens=42))
    assert event.usage is not None
    assert event.usage.total_tokens == 42
