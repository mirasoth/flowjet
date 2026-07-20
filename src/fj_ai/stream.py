"""Stream agent events: ephemeral progress, then final answer only."""

from __future__ import annotations

import json
import sys
import warnings
from typing import Any, TextIO

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from soothe_nano import CodingCoreAgent

from fj_ai.progress import (
    ProgressLine,
    friendly_progress,
    friendly_tool_call,
    friendly_tool_result,
)


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


def _tool_call_name(tc: Any) -> str:
    if isinstance(tc, dict):
        return str(tc.get("name") or "unknown")
    return str(getattr(tc, "name", None) or "unknown")


def _tool_call_args(tc: Any) -> Any:
    if isinstance(tc, dict):
        return tc.get("args")
    return getattr(tc, "args", None)


async def stream_query(
    agent: CodingCoreAgent,
    query: str,
    *,
    thread_id: str,
    show_tool_calls: bool = False,
    out: TextIO | None = None,
    err: TextIO | None = None,
    progress: ProgressLine | None = None,
) -> str:
    """Run a query with ephemeral progress; print only the final answer."""
    stdout = out or sys.stdout
    stderr = err or sys.stderr
    status = progress if progress is not None else ProgressLine(stdout)
    messages = [HumanMessage(content=query)]
    config = {"configurable": {"thread_id": thread_id}}
    answer_buf = ""
    pending_tool_names: dict[str, str] = {}
    pending_tool_args: dict[str, Any] = {}
    last_tool_name: str | None = None
    last_tool_args: Any | None = None

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
                        tool_calls = getattr(message_obj, "tool_calls", None) or []
                        if tool_calls:
                            # New tool-calling turn — final prose comes after tools.
                            answer_buf = ""
                            for tc in tool_calls:
                                name = _tool_call_name(tc)
                                tc_args = _tool_call_args(tc)
                                tc_id = (
                                    tc.get("id")
                                    if isinstance(tc, dict)
                                    else getattr(tc, "id", None)
                                )
                                if tc_id:
                                    pending_tool_names[str(tc_id)] = name
                                    pending_tool_args[str(tc_id)] = tc_args
                                last_tool_name = name
                                last_tool_args = tc_args
                                label, color = friendly_tool_call(name, tc_args)
                                status.update(label, color=color)
                                if show_tool_calls:
                                    stderr.write(f"  [tool] {name}\n")
                                    stderr.flush()
                        else:
                            answer_buf = accumulate_ai_text(answer_buf, message_obj)
                            if answer_buf:
                                status.update("Writing answer…", color="green")

                    elif isinstance(message_obj, ToolMessage):
                        tc_id = getattr(message_obj, "tool_call_id", None)
                        name = None
                        tc_args = None
                        if tc_id:
                            key = str(tc_id)
                            name = pending_tool_names.pop(key, None)
                            tc_args = pending_tool_args.pop(key, None)
                        name = name or getattr(message_obj, "name", None) or last_tool_name
                        tc_args = tc_args if tc_args is not None else last_tool_args
                        status_code = getattr(message_obj, "status", None)
                        is_error = status_code == "error"
                        label, color = friendly_tool_result(
                            str(name) if name else None,
                            tc_args,
                            is_error=is_error,
                        )
                        status.update(label, color=color)
                        if show_tool_calls:
                            preview = _truncate(_format_content(message_obj.content))
                            stderr.write(f"  [result] {preview}\n")
                            stderr.flush()
            except Exception:
                raise

    if answer_buf:
        stdout.write(answer_buf)
        if not answer_buf.endswith("\n"):
            stdout.write("\n")
        stdout.flush()
    return answer_buf


async def invoke_query(
    agent: CodingCoreAgent,
    query: str,
    *,
    thread_id: str,
    out: TextIO | None = None,
    progress: ProgressLine | None = None,
) -> str:
    """Non-streaming invoke with the same ephemeral progress + final-only output."""
    return await stream_query(
        agent,
        query,
        thread_id=thread_id,
        show_tool_calls=False,
        out=out,
        progress=progress,
    )
