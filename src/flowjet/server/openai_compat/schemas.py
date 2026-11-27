"""Request / FlowJet option schemas."""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProjectionMode = Literal["report", "progress", "developer"]
InteractionMode = Literal["agent", "ask"]

logger = logging.getLogger(__name__)

# Same-value copies of the host attachment limits (soothe-daemon preflight).
MAX_IMAGE_ATTACHMENTS = 8
MAX_IMAGE_ATTACHMENT_BYTES = 20 * 1024 * 1024
ALLOWED_ATTACHMENT_MIME = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/bmp",
    }
)
_ATTACHMENT_MIME_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
}


class FlowjetOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    projection: ProjectionMode = "report"
    session: str | None = None
    metadata: dict[str, Any] | None = None
    interaction_mode: InteractionMode = Field(
        default="agent",
        description=(
            "soothe-nano interaction mode. ``agent`` allows mutating tools; "
            "``ask`` is hard read-only (inspect + answer only)."
        ),
    )


class CreateResponseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    input: str | list[Any]
    stream: bool = False
    flowjet: FlowjetOptions | None = None


class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions request schema.

    Translates the classic ``messages`` array into a single text input
    for the FlowJet backend, then maps the response back to the Chat
    Completions response format.
    """

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    temperature: float | None = None
    flowjet: FlowjetOptions | None = None


def normalize_input(value: str | list[Any]) -> str:
    """Flatten OpenAI-style input into a single text string (Phase 1)."""
    if isinstance(value, str):
        return value
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        # message-like: {role, content}
        content = item.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        elif isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def messages_to_input(messages: list[dict[str, Any]]) -> str:
    """Flatten a Chat Completions ``messages`` array into a single text input.

    Each message is prefixed with its role (``system``, ``user``, ``assistant``,
    ``tool``) so the backend retains conversational context. Multi-part content
    arrays are flattened to their text blocks.
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        text: str
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            chunks: list[str] = []
            for block in content:
                if isinstance(block, str):
                    chunks.append(block)
                elif isinstance(block, dict):
                    t = block.get("text")
                    if isinstance(t, str):
                        chunks.append(t)
            text = "\n".join(chunks)
        else:
            text = str(content)
        parts.append(f"{role}: {text}")
    return "\n".join(parts)


def merge_flowjet_metadata(opts: FlowjetOptions | None) -> dict[str, Any]:
    """Build RunRequest.metadata from FlowJet options (includes interaction_mode)."""
    if opts is None:
        return {"interaction_mode": "agent"}
    meta: dict[str, Any] = dict(opts.metadata or {})
    meta["interaction_mode"] = opts.interaction_mode
    return meta


def _attachment_from_data_url(url: Any) -> dict[str, str] | None:
    """Normalize one data-URL image into an attachment dict (None when unusable)."""
    if not isinstance(url, str) or not url.startswith("data:"):
        return None
    header, _, payload = url.partition(",")
    mime = header[5:].split(";", 1)[0].strip().lower()
    mime = _ATTACHMENT_MIME_ALIASES.get(mime, mime)
    if mime not in ALLOWED_ATTACHMENT_MIME or ";base64" not in header:
        logger.debug("Skipping unsupported image attachment (mime=%s)", mime)
        return None
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        logger.warning("Skipping image attachment with invalid base64 data")
        return None
    if len(raw) > MAX_IMAGE_ATTACHMENT_BYTES:
        logger.warning(
            "Skipping image attachment over %d bytes (%d)",
            MAX_IMAGE_ATTACHMENT_BYTES,
            len(raw),
        )
        return None
    return {"mime_type": mime, "data": payload}


def _image_url_of_block(block: dict[str, Any]) -> Any:
    """Extract the image URL reference from an OpenAI-style content block."""
    if block.get("type") == "image_url":
        ref = block.get("image_url")
        if isinstance(ref, dict):
            return ref.get("url")
        return ref
    if block.get("type") == "input_image":
        return block.get("image_url")
    return None


def _collect_blocks(value: str | list[Any]) -> list[Any]:
    """Flatten wire input into raw content blocks (message-like items unwrapped)."""
    if isinstance(value, str):
        return []
    blocks: list[Any] = []
    for item in value:
        if isinstance(item, str):
            continue
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            blocks.extend(content)
        else:
            blocks.append(item)
    return blocks


def extract_image_attachments(value: str | list[Any]) -> list[dict[str, str]]:
    """Collect normalized image attachments from OpenAI-style wire input.

    Handles both the Responses API ``input`` (message-like items or raw blocks)
    and the Chat Completions ``messages`` array (``role``/``content`` items);
    only inline data-URL images are collected — remote URLs are skipped.

    Returns:
        Up to ``MAX_IMAGE_ATTACHMENTS`` attachment dicts
        (``{"mime_type": ..., "data": <base64>}``).
    """
    attachments: list[dict[str, str]] = []
    for block in _collect_blocks(value):
        if not isinstance(block, dict):
            continue
        if len(attachments) >= MAX_IMAGE_ATTACHMENTS:
            logger.warning("Truncating image attachments at %d", MAX_IMAGE_ATTACHMENTS)
            break
        attachment = _attachment_from_data_url(_image_url_of_block(block))
        if attachment is not None:
            attachments.append(attachment)
    return attachments
