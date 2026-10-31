"""Project Agent Runtime events onto OpenAI / flowjet SSE payloads."""

from __future__ import annotations

import time
from typing import Any

from flowjet.core.events import (
    InterruptWaiting,
    OutputTextDelta,
    Progress,
    RunCompleted,
    RunFailed,
    RunStarted,
    RuntimeEvent,
    ToolCompleted,
    ToolStarted,
    UsageInfo,
)
from flowjet.core.ids import new_message_id
from flowjet.server.clarification import (
    ClarificationFormat,
    build_clarification_payload,
    render_clarification_markdown,
)
from flowjet.server.openai_compat.schemas import ProjectionMode


def empty_usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }


def usage_dict(usage: UsageInfo | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    }


def output_text_part(text: str) -> dict[str, Any]:
    return {"type": "output_text", "text": text, "annotations": []}


def message_item(
    item_id: str,
    *,
    status: str,
    text: str | None = None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if text is not None and status == "completed":
        content = [output_text_part(text)]
    return {
        "type": "message",
        "id": item_id,
        "role": "assistant",
        "status": status,
        "content": content,
    }


class ProjectionEngine:
    def __init__(
        self,
        mode: ProjectionMode,
        response_id: str,
        model: str,
        clarification_format: ClarificationFormat = "markdown",
    ) -> None:
        self.mode = mode
        self.response_id = response_id
        self.model = model
        self.clarification_format = clarification_format
        self.item_id = new_message_id()
        self.created_at = int(time.time())
        self._seq = 0
        self._started = False
        self._text_started = False
        self._output_text = ""
        self._status = "in_progress"
        self._usage: dict[str, Any] | None = None
        self._error_message: str | None = None

    def _next(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        return {"sequence_number": self._seq, **payload}

    def _ensure_lifecycle_start(self) -> list[dict[str, Any]]:
        if self._started:
            return []
        self._started = True
        snap = self._response_snapshot(status="in_progress")
        return [
            self._next({"type": "response.created", "response": snap}),
            self._next({"type": "response.in_progress", "response": snap}),
        ]

    def _ensure_text_headers(self) -> list[dict[str, Any]]:
        if self._text_started:
            return []
        self._text_started = True
        return [
            self._next(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": message_item(self.item_id, status="in_progress"),
                }
            ),
            self._next(
                {
                    "type": "response.content_part.added",
                    "item_id": self.item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "part": output_text_part(""),
                }
            ),
        ]

    def handle(self, event: RuntimeEvent) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        events.extend(self._ensure_lifecycle_start())

        if isinstance(event, RunStarted):
            return events

        if isinstance(event, Progress):
            if self.mode in ("progress", "developer"):
                events.append(
                    self._next(
                        {
                            "type": "response.flowjet.progress",
                            "stage": event.stage,
                            "message": event.message,
                        }
                    )
                )
            return events

        if isinstance(event, InterruptWaiting):
            if self.mode in ("progress", "developer"):
                events.append(
                    self._next(
                        {
                            "type": "response.flowjet.progress",
                            "stage": "Waiting",
                            "message": event.message or "Waiting for input…",
                        }
                    )
                )
            # Structured clarification channel (``json`` / ``both`` formats).
            # Emitted in every projection mode — a clarification is turn
            # content the client must answer, not developer detail.
            if event.questions and self.clarification_format in ("json", "both"):
                events.append(
                    self._next(
                        {
                            "type": "response.flowjet.clarification",
                            "clarification": build_clarification_payload(
                                event.questions, event.interrupt_ids
                            ),
                        }
                    )
                )
            # In ``both`` mode also emit the Markdown block as reply text so
            # generic OpenAI clients (no clarification-widget support) still
            # see the questions in the message they render.
            if event.questions and self.clarification_format == "both":
                block = render_clarification_markdown(event.questions)
                events.extend(self._ensure_text_headers())
                self._output_text += block
                events.append(
                    self._next(
                        {
                            "type": "response.output_text.delta",
                            "item_id": self.item_id,
                            "output_index": 0,
                            "content_index": 0,
                            "delta": block,
                            "logprobs": [],
                        }
                    )
                )
            return events

        if isinstance(event, ToolStarted):
            if self.mode == "developer":
                events.append(
                    self._next(
                        {
                            "type": "response.flowjet.tool.started",
                            "tool": event.tool,
                            "call_id": event.call_id,
                        }
                    )
                )
            return events

        if isinstance(event, ToolCompleted):
            if self.mode == "developer":
                events.append(
                    self._next(
                        {
                            "type": "response.flowjet.tool.completed",
                            "tool": event.tool,
                            "call_id": event.call_id,
                            "ok": event.ok,
                            "duration_ms": event.duration_ms,
                        }
                    )
                )
            return events

        if isinstance(event, OutputTextDelta):
            events.extend(self._ensure_text_headers())
            self._output_text += event.delta
            events.append(
                self._next(
                    {
                        "type": "response.output_text.delta",
                        "item_id": self.item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": event.delta,
                        "logprobs": [],
                    }
                )
            )
            return events

        if isinstance(event, RunCompleted):
            if event.output_text and event.output_text != self._output_text:
                missing = event.output_text[len(self._output_text) :]
                if missing or not self._output_text:
                    events.extend(self._ensure_text_headers())
                    if not self._output_text:
                        self._output_text = event.output_text
                        events.append(
                            self._next(
                                {
                                    "type": "response.output_text.delta",
                                    "item_id": self.item_id,
                                    "output_index": 0,
                                    "content_index": 0,
                                    "delta": event.output_text,
                                    "logprobs": [],
                                }
                            )
                        )
                    elif missing:
                        self._output_text = event.output_text
                        events.append(
                            self._next(
                                {
                                    "type": "response.output_text.delta",
                                    "item_id": self.item_id,
                                    "output_index": 0,
                                    "content_index": 0,
                                    "delta": missing,
                                    "logprobs": [],
                                }
                            )
                        )
            else:
                self._output_text = event.output_text or self._output_text
                events.extend(self._ensure_text_headers())

            self._usage = usage_dict(event.usage) or empty_usage()
            self._status = "completed"
            events.append(
                self._next(
                    {
                        "type": "response.output_text.done",
                        "item_id": self.item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "text": self._output_text,
                        "logprobs": [],
                    }
                )
            )
            events.append(
                self._next(
                    {
                        "type": "response.content_part.done",
                        "item_id": self.item_id,
                        "output_index": 0,
                        "content_index": 0,
                        "part": output_text_part(self._output_text),
                    }
                )
            )
            events.append(
                self._next(
                    {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": message_item(
                            self.item_id, status="completed", text=self._output_text
                        ),
                    }
                )
            )
            events.append(
                self._next(
                    {
                        "type": "response.completed",
                        "response": self.final_response(),
                    }
                )
            )
            return events

        if isinstance(event, RunFailed):
            self._status = "failed"
            self._error_message = event.message
            events.append(
                self._next(
                    {
                        "type": "response.failed",
                        "response": self.final_response(),
                    }
                )
            )
            return events

        return events

    def _response_snapshot(self, status: str | None = None) -> dict[str, Any]:
        st = status or self._status
        body: dict[str, Any] = {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created_at,
            "status": st,
            "model": self.model,
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "output": [],
            "usage": self._usage,
        }
        if st == "completed" and self._output_text:
            body["output"] = [
                message_item(self.item_id, status="completed", text=self._output_text)
            ]
            if body["usage"] is None:
                body["usage"] = empty_usage()
        if st == "failed" and self._error_message:
            body["error"] = {"message": self._error_message}
        return body

    def final_response(self) -> dict[str, Any]:
        return self._response_snapshot()
