"""Clarification (``ask_user``) egress format tests.

``FLOWJET_CLARIFICATION_FORMAT`` selects how a paused ``ask_user`` turn is
presented on each server surface — ``markdown`` (default, the historical
wire), ``json`` (structured payload for frontends), or ``both``. The answer
direction never changes: the next prompt text resumes the paused graph.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest

from flowjet.core.events import (
    InterruptWaiting,
    ModelInfo,
    RunCompleted,
    RunRequest,
    RunStarted,
    RuntimeEvent,
)
from flowjet.server.acp.agent import FlowJetAcpAgent
from flowjet.server.clarification import (
    CLARIFICATION_TYPE,
    CLARIFICATION_URI_PREFIX,
    CLARIFICATION_VERSION,
    build_clarification_payload,
    render_clarification_markdown,
)
from flowjet.server.openai_compat.projection import ProjectionEngine

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_QUESTIONS = (
    {
        "question": "Which auth method?",
        "header": "Auth method",
        "options": [
            {"label": "API key (Recommended)", "description": "Fastest to set up."},
            {"label": "OAuth", "description": "Delegated user access."},
        ],
    },
)
_INTERRUPT_IDS = ("interrupt-abc",)


def _interrupt_event() -> InterruptWaiting:
    return InterruptWaiting(
        message="Waiting for input…",
        questions=_QUESTIONS,
        interrupt_ids=_INTERRUPT_IDS,
    )


@dataclass
class _TextBlock:
    """Stand-in for an ACP text content block."""

    text: str


class _RecordingClient:
    """Minimal ACP client that records every session_update call."""

    def __init__(self) -> None:
        self.updates: list[Any] = []

    async def session_update(self, session_id: str, update: Any) -> None:
        self.updates.append(update)


class _ScriptedBackend:
    """Backend that replays a scripted list of RuntimeEvents."""

    def __init__(self, events: list[RuntimeEvent]) -> None:
        self._events = events

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="default")]

    async def delete_run(self, run_id: str) -> None:
        return None

    async def stream_run(self, request: RunRequest) -> AsyncIterator[RuntimeEvent]:
        for event in self._events:
            yield event


async def _run_prompt(
    events: list[RuntimeEvent],
    clarification_format: str = "markdown",
) -> _RecordingClient:
    backend = _ScriptedBackend(events)
    client = _RecordingClient()
    agent = FlowJetAcpAgent(
        backend=backend,
        client=client,
        clarification_format=clarification_format,  # type: ignore[arg-type]
    )
    await agent.new_session(cwd="/tmp")
    session_id = next(iter(agent._sessions))
    await agent.prompt(session_id, [_TextBlock("hello")])
    return client


def _message_chunks(client: _RecordingClient) -> list[Any]:
    return [
        u for u in client.updates if getattr(u, "session_update", None) == "agent_message_chunk"
    ]


def _resource_chunks(client: _RecordingClient) -> list[Any]:
    """Message chunks whose content is an embedded resource block."""
    return [u for u in _message_chunks(client) if getattr(u.content, "type", None) == "resource"]


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


def test_envelope_shape() -> None:
    payload = build_clarification_payload(_QUESTIONS, _INTERRUPT_IDS)
    assert payload["type"] == CLARIFICATION_TYPE
    assert payload["version"] == CLARIFICATION_VERSION
    assert payload["interrupt_ids"] == ["interrupt-abc"]
    assert payload["questions"][0]["question"] == "Which auth method?"
    assert payload["questions"][0]["header"] == "Auth method"
    assert payload["questions"][0]["options"][0]["label"] == "API key (Recommended)"


def test_envelope_sanitizes_unknown_keys() -> None:
    """A malformed question cannot leak arbitrary shapes to a frontend."""
    payload = build_clarification_payload(
        (
            {
                "question": "Q?",
                "header": "H",
                "options": [{"label": "a", "description": "d", "extra": 1}],
                "junk": "should be dropped",
            },
        ),
        ("", "id2"),  # blank id is dropped
    )
    q = payload["questions"][0]
    assert set(q) == {"question", "header", "options"}
    assert set(q["options"][0]) == {"label", "description"}
    assert payload["interrupt_ids"] == ["id2"]


def test_markdown_renderer_matches_cli_block() -> None:
    block = render_clarification_markdown(_QUESTIONS)
    assert "Which auth method?" in block
    assert "API key (Recommended)" in block


# ---------------------------------------------------------------------------
# ACP surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acp_markdown_format_is_the_default_wire() -> None:
    """Default format emits the Markdown text chunk and nothing structured."""
    client = await _run_prompt(
        [
            RunStarted(run_id="r1", model="default"),
            _interrupt_event(),
            RunCompleted(output_text=""),
        ]
    )
    chunks = _message_chunks(client)
    assert len(chunks) == 1
    assert chunks[0].content.type == "text"
    assert "Which auth method?" in chunks[0].content.text
    assert _resource_chunks(client) == []


@pytest.mark.asyncio
async def test_acp_json_format_emits_resource_block() -> None:
    """``json`` format carries the structured envelope in a resource block."""
    client = await _run_prompt(
        [
            RunStarted(run_id="r1", model="default"),
            _interrupt_event(),
            RunCompleted(output_text=""),
        ],
        clarification_format="json",
    )
    chunks = _message_chunks(client)
    assert len(chunks) == 1
    assert chunks[0].content.type == "resource"
    resource = chunks[0].content.resource
    assert resource.mime_type == "application/json"
    assert resource.uri == f"{CLARIFICATION_URI_PREFIX}interrupt-abc"
    payload = json.loads(resource.text)
    assert payload["type"] == CLARIFICATION_TYPE
    assert payload["version"] == CLARIFICATION_VERSION
    assert payload["interrupt_ids"] == ["interrupt-abc"]
    assert payload["questions"][0]["header"] == "Auth method"


@pytest.mark.asyncio
async def test_acp_both_format_emits_markdown_and_resource() -> None:
    """``both`` emits the Markdown chunk plus the resource block."""
    client = await _run_prompt(
        [
            RunStarted(run_id="r1", model="default"),
            _interrupt_event(),
            RunCompleted(output_text=""),
        ],
        clarification_format="both",
    )
    chunks = _message_chunks(client)
    assert len(chunks) == 2
    text_chunks = [c for c in chunks if c.content.type == "text"]
    assert len(text_chunks) == 1
    assert "Which auth method?" in text_chunks[0].content.text
    resources = [c for c in chunks if c.content.type == "resource"]
    assert len(resources) == 1
    assert resources[0].content.resource.uri.startswith(CLARIFICATION_URI_PREFIX)


@pytest.mark.asyncio
async def test_acp_thought_is_emitted_in_every_format() -> None:
    """The "Waiting for input" thought chunk is format-independent."""
    for fmt in ("markdown", "json", "both"):
        client = await _run_prompt(
            [
                RunStarted(run_id="r1", model="default"),
                _interrupt_event(),
                RunCompleted(output_text=""),
            ],
            clarification_format=fmt,
        )
        thoughts = [
            u.content.text
            for u in client.updates
            if getattr(u, "session_update", None) == "agent_thought_chunk"
        ]
        assert "Waiting for input…" in thoughts, f"format={fmt}"


@pytest.mark.asyncio
async def test_acp_no_questions_emits_thought_only() -> None:
    """A pause without structured questions never emits a resource block."""
    for fmt in ("markdown", "json", "both"):
        client = await _run_prompt(
            [
                RunStarted(run_id="r1", model="default"),
                InterruptWaiting(message="Waiting for input…"),
                RunCompleted(output_text=""),
            ],
            clarification_format=fmt,
        )
        assert _message_chunks(client) == [], f"format={fmt}"


# ---------------------------------------------------------------------------
# OpenAI-compatible surface
# ---------------------------------------------------------------------------


def _drain_projection(
    clarification_format: str,
    mode: str = "report",
) -> tuple[list[dict], ProjectionEngine]:
    eng = ProjectionEngine(
        mode,  # type: ignore[arg-type]
        "resp_1",
        "default",
        clarification_format,  # type: ignore[arg-type]
    )
    out: list[dict] = []
    for event in (
        RunStarted(run_id="resp_1", model="default"),
        _interrupt_event(),
        RunCompleted(output_text=""),
    ):
        out.extend(eng.handle(event))
    return out, eng


def test_projection_markdown_format_is_unchanged() -> None:
    """Default format keeps the historical behavior: no clarification event."""
    events, _ = _drain_projection("markdown")
    types = [e["type"] for e in events]
    assert "response.flowjet.clarification" not in types
    # No output text is synthesized for the pause either.
    assert "response.output_text.delta" not in types


def test_projection_json_emits_clarification_event_in_all_modes() -> None:
    """``json`` emits the structured event — a clarification is turn content,
    not developer detail, so it appears even in ``report`` mode."""
    for mode in ("report", "progress", "developer"):
        events, _ = _drain_projection("json", mode=mode)
        clarifications = [e for e in events if e["type"] == "response.flowjet.clarification"]
        assert len(clarifications) == 1, f"mode={mode}"
        payload = clarifications[0]["clarification"]
        assert payload["type"] == CLARIFICATION_TYPE
        assert payload["version"] == CLARIFICATION_VERSION
        assert payload["interrupt_ids"] == ["interrupt-abc"]
        assert payload["questions"][0]["options"][0]["label"] == "API key (Recommended)"
        # json format does not synthesize reply text.
        deltas = [e for e in events if e["type"] == "response.output_text.delta"]
        assert deltas == [], f"mode={mode}"


def test_projection_both_emits_event_and_markdown_delta() -> None:
    """``both`` adds the Markdown block to the reply text."""
    events, eng = _drain_projection("both")
    clarifications = [e for e in events if e["type"] == "response.flowjet.clarification"]
    assert len(clarifications) == 1
    deltas = [e for e in events if e["type"] == "response.output_text.delta"]
    assert len(deltas) == 1
    assert "Which auth method?" in deltas[0]["delta"]
    # The engine's accumulated text matches, and RunCompleted (empty output)
    # did not wipe it.
    assert "Which auth method?" in eng._output_text


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_parses_clarification_format(monkeypatch: pytest.MonkeyPatch) -> None:
    from flowjet.server.config import Settings

    assert Settings(_env_file=None).clarification_format == "markdown"

    monkeypatch.setenv("FLOWJET_CLARIFICATION_FORMAT", "json")
    assert Settings(_env_file=None).clarification_format == "json"

    monkeypatch.setenv("FLOWJET_CLARIFICATION_FORMAT", "both")
    assert Settings(_env_file=None).clarification_format == "both"


def test_settings_rejects_unknown_format(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    from flowjet.server.config import Settings

    monkeypatch.setenv("FLOWJET_CLARIFICATION_FORMAT", "xml")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
