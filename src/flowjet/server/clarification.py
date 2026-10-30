"""Clarification (``ask_user`` pause) egress projections for the server.

The soothe ``ask_user`` tool pauses the agent graph with a structured interrupt
payload (``{"type": "ask_user", "questions": [...]}``); FlowJet receives it as
an ``InterruptWaiting`` event whose ``questions`` are the already-coerced
``QuestionSpec`` dumps. How that pause is presented to server clients is a
*server egress* concern, selected by ``FLOWJET_CLARIFICATION_FORMAT``:

- ``markdown`` (default) — render the questions as a Markdown agent message.
  This is the historical wire behavior; existing hosts see no change.
- ``json`` — deliver the structured payload instead, so frontends can render
  interactive option widgets rather than parse Markdown. On the ACP surface it
  travels as an ``agent_message_chunk`` with an embedded JSON resource block;
  on the OpenAI-compatible surface as a ``response.flowjet.clarification``
  SSE event.
- ``both`` — the Markdown block plus the structured payload (frontends dedupe
  via the envelope's ``interrupt_ids``).

The answer direction is unchanged in every mode: the client sends the chosen
option label (or free text) as the next prompt, which resumes the paused
graph — no new resume protocol.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal

__all__ = [
    "CLARIFICATION_TYPE",
    "CLARIFICATION_URI_PREFIX",
    "CLARIFICATION_VERSION",
    "ClarificationFormat",
    "build_clarification_payload",
    "clarification_json_text",
    "render_clarification_markdown",
]

#: Server-level egress format selector (``FLOWJET_CLARIFICATION_FORMAT``).
ClarificationFormat = Literal["markdown", "json", "both"]

#: Envelope discriminator — matches the soothe ``ask_user`` interrupt payload.
CLARIFICATION_TYPE = "ask_user"

#: Schema version of the structured envelope, for forward evolution.
CLARIFICATION_VERSION = 1

#: URI prefix of the ACP embedded-resource block, carrying the primary
#: interrupt id so ``both``-mode frontends can correlate it with the envelope.
CLARIFICATION_URI_PREFIX = "flowjet://clarification/"


def _sanitize_question(question: Mapping[str, Any]) -> dict[str, Any]:
    """Project one question onto the stable envelope shape.

    ``InterruptWaiting.questions`` entries are already coerced by soothe's
    ``QuestionSpec`` (header ≤12 chars, 2-4 options, unique labels), but the
    nano bridge only checks ``isinstance(q, dict)`` — picking the known keys
    here keeps a malformed payload from leaking arbitrary shapes to a
    frontend.
    """
    options_out: list[dict[str, str]] = []
    raw_options = question.get("options")
    if isinstance(raw_options, (list, tuple)):
        for opt in raw_options:
            if isinstance(opt, Mapping):
                options_out.append(
                    {
                        "label": str(opt.get("label") or ""),
                        "description": str(opt.get("description") or ""),
                    }
                )
    return {
        "question": str(question.get("question") or ""),
        "header": str(question.get("header") or ""),
        "options": options_out,
    }


def build_clarification_payload(
    questions: Sequence[Mapping[str, Any]],
    interrupt_ids: Sequence[str],
) -> dict[str, Any]:
    """Build the versioned clarification envelope for structured consumers."""
    return {
        "type": CLARIFICATION_TYPE,
        "version": CLARIFICATION_VERSION,
        "interrupt_ids": [str(i) for i in interrupt_ids if str(i).strip()],
        "questions": [_sanitize_question(q) for q in questions],
    }


def clarification_json_text(payload: Mapping[str, Any]) -> str:
    """Serialize the envelope for embedded-resource / SSE transport."""
    return json.dumps(payload, ensure_ascii=False)


def render_clarification_markdown(questions: Sequence[Mapping[str, Any]]) -> str:
    """Render the questions as the Markdown block (the ``markdown`` wire).

    Thin wrapper over the CLI renderer so both server surfaces (ACP,
    OpenAI-compatible) share one call point; the import stays lazy to keep the
    CLI module off the server import path.
    """
    from flowjet.cli.stream import format_questions_markdown

    return format_questions_markdown(tuple(dict(q) for q in questions))
