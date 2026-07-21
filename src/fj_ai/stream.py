"""Stream agent events: ephemeral progress + live answer tokens by default."""

from __future__ import annotations

import json
import sys
import warnings
from typing import Any, TextIO

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from soothe_nano import CodingCoreAgent

from fj_ai.errors import simplify_tool_error, tool_result_error_detail
from fj_ai.progress import (
    ProgressLine,
    friendly_progress,
    friendly_tool_call,
    friendly_tool_result,
)
from fj_ai.tool_stream import ToolCallArgAccumulator


def _truncate(text: str, limit: int = 200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _format_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        try:
            return json.dumps(content, ensure_ascii=False)[:200]
        except (TypeError, ValueError):
            return str(content)[:200]
    return str(content)[:200]


def _ai_text(message: AIMessage) -> str:
    content = message.content
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
    try:
        from soothe_nano.utils.llm.response_text import llm_response_text

        return llm_response_text(message) or ""
    except Exception:
        return str(content) if content else ""


def accumulate_ai_text(current: str, message: AIMessage) -> str:
    """Merge streamed AI text.

    ``messages`` mode often yields ``AIMessageChunk`` deltas. Replacing with each
    chunk leaves only the last token fragment — accumulate instead.
    """
    text = _ai_text(message)
    if not text:
        return current

    if isinstance(message, AIMessageChunk):
        # Cumulative snapshot (some providers) vs pure delta.
        if current and text.startswith(current):
            return text
        if current and current.startswith(text) and len(current) >= len(text):
            # Out-of-order / shorter replay — keep longer buffer.
            return current
        return current + text

    # Full AIMessage: take as the current turn's complete text.
    return text


class AnswerWriter:
    """Buffer answer text and optionally emit tokens as they arrive."""

    def __init__(
        self,
        stdout: TextIO,
        status: ProgressLine,
        *,
        live: bool = True,
    ) -> None:
        self.buf = ""
        self._stdout = stdout
        self._status = status
        self._live = live
        self._emitted = ""
        self._live_active = False

    def set(self, new_buf: str) -> None:
        """Replace the answer buffer; stream any new suffix when ``live``."""
        self.buf = new_buf
        if not self._live or not new_buf:
            if new_buf and not self._live:
                self._status.update("Writing answer…", color="green")
            return

        if not self._live_active:
            # Hand stdout from the spinner to the answer stream.
            self._status.release()
            self._live_active = True

        if new_buf.startswith(self._emitted):
            delta = new_buf[len(self._emitted) :]
        elif self._emitted.startswith(new_buf):
            delta = ""
        else:
            # Divergent replace after partial emit — start a new paragraph.
            if self._emitted and not self._emitted.endswith("\n"):
                self._stdout.write("\n")
            delta = new_buf
            self._emitted = ""

        if delta:
            self._stdout.write(delta)
            self._stdout.flush()
        self._emitted = new_buf

    def reset_for_tools(self) -> None:
        """Drop buffered answer when a tool call starts.

        Already-emitted live text stays on screen; progress resumes on a new line.
        """
        if self._live and self._live_active and self._emitted and not self._emitted.endswith("\n"):
            self._stdout.write("\n")
            self._stdout.flush()
        self.buf = ""
        self._emitted = ""
        self._live_active = False

    def finish(self) -> str:
        """Flush remaining output and return the final answer buffer."""
        if not self._live:
            if self.buf:
                self._stdout.write(self.buf)
                if not self.buf.endswith("\n"):
                    self._stdout.write("\n")
                self._stdout.flush()
        elif self._emitted and not self._emitted.endswith("\n"):
            self._stdout.write("\n")
            self._stdout.flush()
        return self.buf


async def stream_query(
    agent: CodingCoreAgent,
    query: str,
    *,
    thread_id: str,
    show_tool_calls: bool = False,
    live_answer: bool = True,
    out: TextIO | None = None,
    err: TextIO | None = None,
    progress: ProgressLine | None = None,
) -> str:
    """Run a query with ephemeral progress and a streamed (or final) answer."""
    stdout = out or sys.stdout
    stderr = err or sys.stderr
    status = progress if progress is not None else ProgressLine(stdout)
    messages = [HumanMessage(content=query)]
    config = {"configurable": {"thread_id": thread_id}}
    answer = AnswerWriter(stdout, status, live=live_answer)
    tool_args = ToolCallArgAccumulator()
    last_tool_name: str | None = None
    last_tool_args: dict[str, Any] = {}
    last_progress_key = ""

    # Deepagents emits a deprecation warning mid-run that would smash the
    # ephemeral progress line when mixed onto the terminal.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            module=r"soothe_deepagents\.middleware\.filesystem",
        )
        warnings.filterwarnings(
            "ignore",
            message=r".*Passing a callable \(factory\) as `backend`.*",
        )
        async with status:
            status.update("Thinking…", color="cyan")
            try:
                async for chunk in agent.astream(
                    {"messages": messages},
                    config=config,
                    stream_mode=["messages", "updates", "custom"],
                    subgraphs=True,
                ):
                    if not isinstance(chunk, tuple) or len(chunk) != 3:
                        continue

                    _namespace, mode, data = chunk

                    if mode == "custom" and isinstance(data, dict):
                        mapped = friendly_progress(data)
                        if mapped:
                            label, color = mapped
                            status.update(label, color=color)
                        if show_tool_calls:
                            event_type = data.get("type", "unknown")
                            stderr.write(f"  [event] {event_type}\n")
                            stderr.flush()
                        continue

                    if mode == "updates" and isinstance(data, dict) and "__interrupt__" in data:
                        status.update("Waiting for input…", color="yellow")
                        if show_tool_calls:
                            stderr.write("\n  [interrupted] agent paused for input\n")
                            stderr.flush()
                        continue

                    if mode != "messages":
                        continue
                    if not isinstance(data, tuple) or len(data) != 2:
                        continue
                    message_obj, _metadata = data

                    if isinstance(message_obj, AIMessage):
                        # Tool args stream as tool_call_chunks (partial JSON). Accumulate
                        # and refresh the progress line as args become available.
                        updates = tool_args.ingest_message(message_obj)
                        if updates:
                            answer.reset_for_tools()
                            for tc_id, name, args in updates:
                                last_tool_name = name
                                last_tool_args = args
                                label, color = friendly_tool_call(name, args)
                                progress_key = f"{tc_id}:{label}"
                                if progress_key != last_progress_key:
                                    status.update(label, color=color)
                                    last_progress_key = progress_key
                                if show_tool_calls and args:
                                    stderr.write(f"  [tool] {name} {args}\n")
                                    stderr.flush()
                        elif not (
                            getattr(message_obj, "tool_calls", None)
                            or getattr(message_obj, "tool_call_chunks", None)
                        ):
                            answer.set(accumulate_ai_text(answer.buf, message_obj))

                    elif isinstance(message_obj, ToolMessage):
                        tc_id = getattr(message_obj, "tool_call_id", None)
                        name, tc_args = tool_args.pop(tc_id)
                        name = name or getattr(message_obj, "name", None) or last_tool_name
                        if not tc_args:
                            tc_args = last_tool_args
                        else:
                            last_tool_args = tc_args
                        if name:
                            last_tool_name = str(name)
                        status_code = getattr(message_obj, "status", None)
                        err_detail = tool_result_error_detail(message_obj.content)
                        is_error = status_code == "error" or err_detail is not None
                        short_err = simplify_tool_error(err_detail) if err_detail else None
                        label, color = friendly_tool_result(
                            str(name) if name else None,
                            tc_args,
                            is_error=is_error,
                            detail=short_err,
                        )
                        status.update(label, color=color)
                        last_progress_key = ""
                        if show_tool_calls:
                            preview = short_err or _truncate(_format_content(message_obj.content))
                            tag = "error" if is_error else "result"
                            stderr.write(f"  [{tag}] {preview}\n")
                            stderr.flush()
            except Exception:
                raise

    return answer.finish()


async def invoke_query(
    agent: CodingCoreAgent,
    query: str,
    *,
    thread_id: str,
    out: TextIO | None = None,
    progress: ProgressLine | None = None,
) -> str:
    """Non-streaming answer write: progress until done, then print the final text."""
    return await stream_query(
        agent,
        query,
        thread_id=thread_id,
        show_tool_calls=False,
        live_answer=False,
        out=out,
        progress=progress,
    )
