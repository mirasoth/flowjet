"""Human-facing formatting helpers used while mapping runtime streams.

These are the presentation concerns of the bridge layer: one-line tool
summaries, step progress labels, AI text extraction and word-boundary delta
chunking. The stream *semantics* (which chunk becomes which event) stay in
:mod:`flowjet.core.bridges.nano.mapping`.
"""

from __future__ import annotations

from typing import Any

from flowjet.core.events import OutputTextDelta

# Arg keys worth echoing in a one-line tool summary (first match wins).
_TOOL_SUMMARY_KEYS = (
    "file_path",
    "path",
    "target_file",
    "command",
    "cmd",
    "script",
    "query",
    "pattern",
    "url",
    "skill",
)


class ToolCallSummarizer:
    """``write_file a.txt``-style one-line summaries for status lines."""

    @classmethod
    def summarize(cls, name: str, args: dict[str, Any]) -> str:
        for key in _TOOL_SUMMARY_KEYS:
            value = args.get(key)
            if isinstance(value, (str, int, float)) and str(value).strip():
                text = " ".join(str(value).split())
                return f"{name} {text[:60]}"
        return str(name)


class StepProgressFormatter:
    """Human-readable one-liners for step payloads (non-CLI renderers)."""

    @staticmethod
    def message(payload: dict[str, Any]) -> str:
        step = payload.get("step")
        steps = payload.get("steps")
        todo = str(payload.get("todo") or "").strip()
        head = f"{step}/{steps}" if step and steps else "step"
        if todo:
            return f"Step {head} · {todo}"
        if payload.get("status") == "completed":
            return f"Steps complete · {head}"
        return f"Step {head}"


class OutputTextChunker:
    """Split committed text into word-boundary chunks for streaming.

    Protocol projections (ACP ``agent_message_chunk``, OpenAI SSE
    ``response.output_text.delta``) forward each delta as a separate
    notification. Splitting on word boundaries (keeping the trailing space)
    gives the client a natural token-by-token feel without the complexity of
    true incremental streaming (which would require a discard/reset mechanism
    for narration text that tool calls supersede).
    """

    @staticmethod
    def word_deltas(text: str) -> list[OutputTextDelta]:
        if not text:
            return []
        if len(text) <= 1:
            return [OutputTextDelta(delta=text)]
        deltas: list[OutputTextDelta] = []
        pos = 0
        while pos < len(text):
            # Find the next space after the current position.
            end = text.find(" ", pos)
            if end == -1:
                deltas.append(OutputTextDelta(delta=text[pos:]))
                break
            # Include the space in this chunk.
            end += 1
            deltas.append(OutputTextDelta(delta=text[pos:end]))
            pos = end
        return deltas


class AiTextExtractor:
    """Extract the plain text of an AI message across content block shapes."""

    @staticmethod
    def text(message: Any) -> str:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return ""


__all__ = ["AiTextExtractor", "OutputTextChunker", "StepProgressFormatter", "ToolCallSummarizer"]
