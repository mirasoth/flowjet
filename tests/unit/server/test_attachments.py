"""Tests for wire image attachment extraction and landing."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from soothe.workspace.attachments import ATTACHMENTS_DIR

from flowjet.core.runtime.isolation.backend import _landed_input_text
from flowjet.server.acp.agent import _extract_prompt_attachments
from flowjet.server.openai_compat.schemas import extract_image_attachments

TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

_PNG_DATA_URL = f"data:image/png;base64,{TINY_PNG_B64}"


def test_extract_from_chat_completions_messages() -> None:
    messages = [
        {"role": "system", "content": "you are helpful"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look at this"},
                {"type": "image_url", "image_url": {"url": _PNG_DATA_URL}},
            ],
        },
    ]
    attachments = extract_image_attachments(messages)
    assert attachments == [{"mime_type": "image/png", "data": TINY_PNG_B64}]


def test_extract_from_responses_input_blocks() -> None:
    value = [
        {"type": "input_text", "text": "describe"},
        {"type": "input_image", "image_url": _PNG_DATA_URL},
        {"type": "input_image", "image_url": "https://example.com/remote.png"},
    ]
    attachments = extract_image_attachments(value)
    # Remote URLs are skipped — only inline data URLs are collected.
    assert attachments == [{"mime_type": "image/png", "data": TINY_PNG_B64}]


def test_extract_string_input_returns_empty() -> None:
    assert extract_image_attachments("plain text") == []


def test_extract_rejects_invalid_payloads() -> None:
    value = [
        {"type": "input_image", "image_url": "data:image/svg+xml;base64,PHN2Zw=="},
        {"type": "input_image", "image_url": "data:image/png;base64,not!!!b64"},
    ]
    assert extract_image_attachments(value) == []


def test_extract_normalizes_jpg_alias() -> None:
    value = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpg;base64,{TINY_PNG_B64}"}}
            ],
        }
    ]
    attachments = extract_image_attachments(value)
    assert attachments == [{"mime_type": "image/jpeg", "data": TINY_PNG_B64}]


def test_extract_acp_image_blocks() -> None:
    class _ImageBlock:
        data = TINY_PNG_B64
        mime_type = "image/png"

    class _TextBlock:
        text = "hello"

    class _AudioBlock:
        data = "AAAA"
        mime_type = "audio/wav"

    attachments = _extract_prompt_attachments([_TextBlock(), _ImageBlock(), _AudioBlock()])
    assert attachments == [{"mime_type": "image/png", "data": TINY_PNG_B64}]


def test_landed_input_text_writes_files_and_appends_note(tmp_path: Path) -> None:
    raw = base64.b64decode(TINY_PNG_B64)
    digest = hashlib.sha256(raw).hexdigest()[:16]
    attachments = ({"mime_type": "image/png", "data": TINY_PNG_B64},)

    out = _landed_input_text("sess-1", tmp_path, "describe this", attachments)
    rel = f"{ATTACHMENTS_DIR}/{digest}.png"
    assert (tmp_path / rel).read_bytes() == raw
    assert out.startswith("describe this")
    assert rel in out
    assert "analyze_image" in out

    # Idempotent: re-landing the same payload keeps the same paths.
    out2 = _landed_input_text("sess-1", tmp_path, "again", attachments)
    assert rel in out2


def test_landed_input_text_failure_degrades_to_original(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "soothe.workspace.attachments.land_attachments",
        None,  # not callable — forces the landing failure path
    )
    out = _landed_input_text(
        "sess-1", tmp_path, "keep me", ({"mime_type": "image/png", "data": TINY_PNG_B64},)
    )
    assert out == "keep me"
