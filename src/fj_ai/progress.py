"""Ephemeral colored progress line for fj (stdout line 1)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
from typing import Any, TextIO

# ANSI
_RESET = "\033[0m"
_BOLD = "\033[1m"
_COLORS = {
    "cyan": "\033[36m",
    "yellow": "\033[33m",
    "magenta": "\033[35m",
    "green": "\033[32m",
    "red": "\033[31m",
    "blue": "\033[34m",
    "white": "\033[37m",
}

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_TICK_SECONDS = 0.08
_SKIP_ARG_KEYS = frozenset(
    {
        "_raw",
        "_subgraph_tool",
        "value",
        "tool_call_id",
        "id",
        "type",
        "index",
    }
)

# Friendly verb for soothe event action suffixes
_ACTION_LABELS: dict[str, str] = {
    "started": "Starting",
    "completed": "Finished",
    "failed": "Failed",
    "error": "Error",
    "cancelled": "Cancelled",
    "iterated": "Working",
    "created": "Created",
    "classified": "Classified",
    "requested": "Waiting",
    "answered": "Resumed",
    "queued": "Queued",
}

# Verb + color for well-known tools (fallback: Running / yellow)
_TOOL_VERBS: dict[str, tuple[str, str]] = {
    "read_file": ("Reading", "yellow"),
    "write_file": ("Writing", "yellow"),
    "edit_file": ("Editing", "yellow"),
    "ls": ("Listing", "yellow"),
    "list_files": ("Listing", "yellow"),
    "glob": ("Globbing", "yellow"),
    "search_files": ("Globbing", "yellow"),
    "grep": ("Grepping", "yellow"),
    "run_command": ("Running", "yellow"),
    "shell": ("Running", "yellow"),
    "bash": ("Running", "yellow"),
    "web_search": ("Searching", "yellow"),
    "search_web": ("Searching", "yellow"),
    "fetch_url": ("Fetching", "yellow"),
    "http_request": ("Requesting", "yellow"),
    "search_tools": ("Finding tools", "blue"),
    "search_skills": ("Finding skills", "blue"),
    "invoke_skill": ("Invoking skill", "blue"),
    "task": ("Delegating", "magenta"),
}


def _color_enabled(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FJ_FORCE_COLOR") in {"1", "true", "yes"}:
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def _line_budget() -> int:
    """Max visible chars for the status text (spinner + margin excluded)."""
    try:
        cols = shutil.get_terminal_size(fallback=(100, 24)).columns
    except OSError:
        cols = 100
    return max(40, min(120, cols - 6))


def _truncate(text: str, limit: int | None = None) -> str:
    limit = _line_budget() if limit is None else limit
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _compact(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value.strip())
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        if all(isinstance(x, (str, int, float, bool)) or x is None for x in value[:5]):
            inner = ", ".join(_compact(x) for x in value[:5])
            if len(value) > 5:
                inner += ", …"
            return inner
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _abbrev_path(path: str) -> str:
    try:
        from soothe_sdk.utils.formatting import convert_and_abbreviate_path

        return convert_and_abbreviate_path(path)
    except Exception:
        home = os.path.expanduser("~")
        if path.startswith(home + os.sep):
            return "~" + path[len(home) :]
        return path


def _tool_meta(name: str) -> Any | None:
    try:
        from soothe_sdk.tools.metadata import get_tool_meta

        return get_tool_meta(name)
    except Exception:
        return None


def _display_name(name: str) -> str:
    try:
        from soothe_sdk.utils import get_tool_display_name

        return get_tool_display_name(name)
    except Exception:
        return name.replace("_", " ").title()


def _normalize_args(args: Any) -> dict[str, Any]:
    """Coerce tool-call args (dict / JSON string / partial) into a flat dict."""
    if args is None:
        return {}
    if isinstance(args, str):
        text = args.strip()
        if not text:
            return {}
        try:
            loaded = json.loads(text)
        except (TypeError, ValueError):
            return {"_text": text}
        if isinstance(loaded, dict):
            return loaded
        return {"_text": text}
    if isinstance(args, dict):
        # Nested ``value`` may hold JSON from some adapters.
        if "value" in args and isinstance(args["value"], str) and args["value"].strip():
            try:
                loaded = json.loads(args["value"])
            except (TypeError, ValueError):
                loaded = None
            if isinstance(loaded, dict):
                merged = {k: v for k, v in args.items() if k != "value"}
                merged.update(loaded)
                return merged
        return dict(args)
    return {"_text": _compact(args)}


def _ordered_arg_keys(tool_name: str, args: dict[str, Any]) -> list[str]:
    meta = _tool_meta(tool_name)
    ordered: list[str] = []
    preferred: tuple[str, ...] = ()
    if meta is not None and getattr(meta, "arg_keys", None):
        preferred = tuple(meta.arg_keys)
    # Sensible defaults when meta is missing.
    if not preferred:
        preferred = (
            "command",
            "cmd",
            "script",
            "file_path",
            "path",
            "target_file",
            "pattern",
            "query",
            "url",
            "regex",
            "old_string",
            "new_string",
            "content",
            "skill",
            "description",
            "prompt",
            "subagent_type",
            "_text",
        )
    for key in preferred:
        if key in args and key not in _SKIP_ARG_KEYS:
            ordered.append(key)
    for key in sorted(args.keys()):
        if key not in ordered and key not in _SKIP_ARG_KEYS:
            ordered.append(key)
    return ordered


def _format_arg_value(tool_name: str, key: str, value: Any) -> str:
    text = _compact(value)
    if not text:
        return ""
    meta = _tool_meta(tool_name)
    path_keys = set(getattr(meta, "path_arg_keys", ()) or ())
    if key in path_keys or key in {
        "file_path",
        "path",
        "target_file",
        "directory",
        "target_directory",
        "dir",
        "filepath",
        "filename",
        "relative_path",
    }:
        return _abbrev_path(text)
    # Quote patterns / queries for readability.
    if key in {"pattern", "query", "regex", "regexp", "old_string", "new_string", "skill"}:
        if not (text.startswith(("'", '"')) and text.endswith(("'", '"'))):
            text = f"“{_truncate(text, 36)}”" if len(text) > 36 else f"“{text}”"
        return text
    if key in {"command", "cmd", "script"}:
        return f"`{_truncate(text, 64)}`"
    if key in {"content", "new_string", "old_string"}:
        return _truncate(text, 28)
    return _truncate(text, 48)


def format_args_preview(tool_name: str, args: Any | None, *, max_parts: int = 3) -> str:
    """Human-readable arg summary, e.g. ``src/cli.py`` or ``“TODO” in src/``."""
    clean = _normalize_args(args)
    if not clean:
        return ""

    # Tool-specific compact shapes
    canonical = tool_name
    meta = _tool_meta(tool_name)
    if meta is not None:
        canonical = meta.name

    parts: list[str] = []
    for key in _ordered_arg_keys(canonical, clean):
        text = _format_arg_value(canonical, key, clean[key])
        if not text:
            continue
        if not parts:
            # Primary arg: bare value
            parts.append(text)
        elif key in {"path", "file_path", "directory", "target_directory", "dir"} and parts:
            # Grep/glob style: pattern in path
            if canonical in {"grep", "glob"} and " in " not in parts[0]:
                parts[0] = f"{parts[0]} in {text}"
            else:
                parts.append(f"{key}={text}")
        elif key in {"old_string", "new_string"} and canonical == "edit_file":
            # Keep edits short: show old→new once
            if key == "old_string":
                parts.append(f"replace {text}")
            elif key == "new_string" and any(p.startswith("replace ") for p in parts):
                parts = [p for p in parts if not p.startswith("replace ")] + [f"replace → {text}"]
            else:
                parts.append(f"{key}={text}")
        else:
            parts.append(f"{key}={text}")
        if len(parts) >= max_parts:
            break

    preview = " · ".join(parts)
    return _truncate(preview)


def format_tool_activity(tool_name: str, args: Any | None = None) -> tuple[str, str]:
    """Status line for an in-flight tool call: ``Reading ~/a.py``."""
    name = (tool_name or "tool").strip() or "tool"
    verb, color = _TOOL_VERBS.get(name, ("Running", "yellow"))
    # Prefer canonical name from meta for verb lookup / display
    meta = _tool_meta(name)
    if meta is not None:
        verb, color = _TOOL_VERBS.get(meta.name, (verb, color))
        name = meta.name

    preview = format_args_preview(name, args)
    display = _display_name(name)
    if preview:
        # Prefer verb + args for known tools; include display name when verb is generic.
        if name in _TOOL_VERBS or (meta is not None and meta.name in _TOOL_VERBS):
            label = f"{verb} {preview}"
        else:
            label = f"{verb} {display} · {preview}"
    else:
        label = f"{verb} {display}"
    return _truncate(label), color


def format_tool_done(
    tool_name: str | None,
    args: Any | None = None,
    *,
    is_error: bool = False,
) -> tuple[str, str]:
    """Status after a tool returns — keep context while model thinks."""
    name = (tool_name or "tool").strip() or "tool"
    preview = format_args_preview(name, args, max_parts=2)
    display = _display_name(name)
    summary = f"{display}({preview})" if preview else display
    if is_error:
        return _truncate(f"Failed {summary}"), "red"
    return _truncate(f"Thinking… · after {summary}"), "cyan"


def _tool_name(data: dict[str, Any]) -> str | None:
    for key in ("tool", "tool_name", "name"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _event_args(data: dict[str, Any]) -> dict[str, Any]:
    """Pull arg-like fields from a soothe custom event."""
    raw = data.get("args")
    if isinstance(raw, dict):
        return dict(raw)
    collected: dict[str, Any] = {}
    for key in (
        "command",
        "cmd",
        "script",
        "file_path",
        "path",
        "file",
        "url",
        "query",
        "pattern",
        "regex",
        "action_preview",
        "skill",
        "message",
        "prompt",
        "description",
        "subagent_type",
        "old_string",
        "new_string",
    ):
        if key in data and data[key] not in (None, ""):
            collected[key] = data[key]
    return collected


def friendly_progress(data: dict[str, Any]) -> tuple[str, str] | None:
    """Map a soothe-nano custom event to ``(label, color)`` or ``None`` to skip."""
    if not isinstance(data, dict):
        return None
    event_type = str(data.get("type") or "").strip()
    if not event_type:
        return None

    # Skip noisy / internal stream plumbing
    if event_type in {"soothe.stream.end", "soothe.protocol.message.received"}:
        return None
    if event_type.startswith("soothe.output."):
        return None

    short = event_type[7:] if event_type.startswith("soothe.") else event_type
    parts = short.split(".")
    domain = parts[0] if parts else "agent"
    action = parts[-1] if parts else ""
    verb = _ACTION_LABELS.get(action, action.replace("_", " ").title() or "Working")

    tool = _tool_name(data)
    args = _event_args(data)
    subagent = None
    if domain == "subagent" and len(parts) >= 2:
        subagent = parts[1]
    elif "subagent" in data and isinstance(data["subagent"], str):
        subagent = data["subagent"]
    elif "subagent_type" in data and isinstance(data["subagent_type"], str):
        subagent = data["subagent_type"]

    if domain in {"tool", "mcp"}:
        name = tool or (parts[1] if len(parts) > 1 else "tool")
        if action in {"completed", "finished"}:
            return format_tool_done(name, args)
        if action in {"failed", "error"}:
            return format_tool_done(name, args, is_error=True)
        return format_tool_activity(name, args)

    if domain == "subagent" or "wired_subagent" in short:
        color = "magenta"
        name = subagent or tool or "subagent"
        preview = format_args_preview(name, args) if args else ""
        detail = preview or _truncate(
            _compact(data.get("action_preview") or data.get("query") or "")
        )
        if action in {"completed", "finished"}:
            label = f"Thinking… · after {name}"
            color = "cyan"
        else:
            label = f"Delegating to {name}" if not action else f"{verb} {name}"
            if detail:
                label = f"{label} · {detail}"
        return _truncate(label), color

    if domain == "skill" or "skill" in short:
        color = "blue"
        name = data.get("skill") or data.get("name") or "skill"
        label = f"{verb} skill {name}"
        return _truncate(label), color

    if domain in {"error"} or action in {"failed", "error"}:
        color = "red"
        err = data.get("error") or data.get("message") or short
        label = f"Error · {_truncate(_compact(err), 64)}"
        return label, color

    if domain == "cognition":
        color = "cyan"
        if "plan" in short:
            label = "Planning…"
        elif "goal" in short and action == "completed":
            color = "green"
            label = "Goal complete"
        elif "strange_loop" in short:
            label = "Thinking…"
        elif "intent" in short:
            intent = data.get("intent") or data.get("label") or data.get("message")
            label = f"Understanding… · {_compact(intent)}" if intent else "Understanding…"
        else:
            label = f"{verb}…"
        return _truncate(label), color

    label = f"{verb}…"
    if tool:
        return format_tool_activity(tool, args)
    detail = format_args_preview("tool", args) if args else ""
    if detail:
        label = f"{verb} · {detail}"
    return _truncate(label), "cyan"


def friendly_tool_call(name: str, args: Any | None = None) -> tuple[str, str]:
    return format_tool_activity(name, args)


def friendly_tool_result(
    name: str | None,
    args: Any | None = None,
    *,
    is_error: bool = False,
) -> tuple[str, str]:
    return format_tool_done(name, args, is_error=is_error)


class ProgressLine:
    """Overwrite a single ephemeral status line on stdout (TTY only).

    A background asyncio tick keeps the spinner moving between stream events
    (e.g. while waiting on the model after a tool result).
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        enabled: bool | None = None,
        tick_seconds: float = _TICK_SECONDS,
    ) -> None:
        self._stream = stream if stream is not None else sys.stdout
        if enabled is None:
            enabled = bool(getattr(self._stream, "isatty", lambda: False)())
        self._enabled = enabled
        self._color = _color_enabled(self._stream) if self._enabled else False
        self._active = False
        self._frame = 0
        self._message = "Working…"
        self._style = "cyan"
        self._tick_seconds = tick_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def __aenter__(self) -> ProgressLine:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()

    async def start(self) -> None:
        """Start the background spinner ticker."""
        if not self._enabled or self._task is not None:
            return
        self._active = True
        self._paint()
        self._task = asyncio.create_task(self._spin(), name="fj-progress-spinner")

    async def stop(self) -> None:
        """Stop the ticker and clear the line."""
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.clear()

    async def _spin(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._tick_seconds)
                if self._active:
                    self._paint()
        except asyncio.CancelledError:
            raise

    def update(self, message: str, *, color: str = "cyan") -> None:
        if not self._enabled:
            return
        self._message = message.strip() or "Working…"
        self._style = color
        self._active = True
        self._paint()
        self._ensure_ticker()

    def _ensure_ticker(self) -> None:
        if not self._enabled or self._task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._task = loop.create_task(self._spin(), name="fj-progress-spinner")

    def _paint(self) -> None:
        if not self._enabled:
            return
        text = self._message
        frame = _SPINNER[self._frame % len(_SPINNER)]
        self._frame += 1
        if self._color:
            code = _COLORS.get(self._style, _COLORS["cyan"])
            rendered = f"{code}{_BOLD}{frame}{_RESET}{code} {text}{_RESET}"
        else:
            rendered = f"{frame} {text}"
        self._stream.write(f"\r\033[2K{rendered}")
        self._stream.flush()

    def clear(self) -> None:
        self._active = False
        if not self._enabled:
            return
        if self._frame > 0 or self._message:
            self._stream.write("\r\033[2K")
            self._stream.flush()
        self._message = ""
