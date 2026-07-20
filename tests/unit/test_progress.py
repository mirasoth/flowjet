"""Tests for ephemeral progress formatting."""

from __future__ import annotations

import asyncio
from io import StringIO

import pytest

from fj_ai.progress import (
    ProgressLine,
    format_args_preview,
    format_tool_activity,
    friendly_progress,
    friendly_tool_call,
    friendly_tool_result,
)


def test_friendly_tool_started_event() -> None:
    label, color = friendly_progress(
        {
            "type": "soothe.tool.invocation.started",
            "tool": "read_file",
            "path": "/tmp/hello.py",
        }
    )
    assert "Reading" in label or "hello.py" in label
    assert "hello.py" in label
    assert color == "yellow"


def test_friendly_subagent() -> None:
    label, color = friendly_progress(
        {"type": "soothe.subagent.explore.started", "query": "find auth"}
    )
    assert "explore" in label.lower()
    assert color == "magenta"


def test_friendly_skip_stream_end() -> None:
    assert friendly_progress({"type": "soothe.stream.end"}) is None


def test_friendly_cognition_thinking() -> None:
    label, color = friendly_progress({"type": "soothe.cognition.strange_loop.started"})
    assert "Thinking" in label
    assert color == "cyan"


def test_format_read_file_activity() -> None:
    label, color = format_tool_activity(
        "read_file", {"file_path": "/Users/chenxm/Workspace/fj-ai/src/fj_ai/cli.py"}
    )
    assert label.startswith("Reading ")
    assert "cli.py" in label
    assert color == "yellow"


def test_format_run_command_activity() -> None:
    label, color = friendly_tool_call("run_command", {"command": "ruff check src/ tests/"})
    assert "Running" in label
    assert "ruff check" in label
    assert color == "yellow"


def test_format_grep_activity() -> None:
    label, _color = format_tool_activity("grep", {"pattern": "ProgressLine", "path": "src/fj_ai"})
    assert "Grepping" in label
    assert "ProgressLine" in label
    assert "src/fj_ai" in label


def test_format_args_preview_primary() -> None:
    preview = format_args_preview("write_file", {"file_path": "nano.yml", "content": "x" * 80})
    assert "nano.yml" in preview


def test_progress_respects_width_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FJ_PROGRESS_WIDTH", "40")
    long_path = "/Users/chenxm/Workspace/fj-ai/src/fj_ai/" + ("very_long_dir/" * 8) + "cli.py"
    label, _color = format_tool_activity("read_file", {"file_path": long_path})
    assert len(label) <= 40
    assert label.startswith("Reading ")
    assert "cli.py" in label  # basename preserved


def test_truncate_path_keeps_basename() -> None:
    from fj_ai.progress import _truncate_path

    out = _truncate_path("/a/b/c/d/e/f/g/important.py", 18)
    assert out.endswith("important.py") or "important.py" in out
    assert len(out) <= 18


def test_friendly_tool_result_keeps_context() -> None:
    label, color = friendly_tool_result(
        "read_file", {"file_path": "src/fj_ai/progress.py"}, is_error=False
    )
    assert "Thinking" in label
    assert "progress.py" in label or "ReadFile" in label
    assert color == "cyan"


def test_friendly_tool_completed_keeps_context() -> None:
    label, color = friendly_progress(
        {
            "type": "soothe.tool.invocation.completed",
            "tool": "read_file",
            "file_path": "Makefile",
        }
    )
    assert "Thinking" in label
    assert "Makefile" in label or "ReadFile" in label
    assert color == "cyan"


def test_progress_line_ephemeral_clear() -> None:
    buf = StringIO()
    line = ProgressLine(buf, enabled=True)
    line.update("Thinking…", color="cyan")
    assert "\r" in buf.getvalue()
    assert "Thinking" in buf.getvalue()
    line.clear()
    assert buf.getvalue().endswith("\033[2K") or "\033[2K" in buf.getvalue()


@pytest.mark.asyncio
async def test_progress_line_spins_between_updates() -> None:
    buf = StringIO()
    line = ProgressLine(buf, enabled=True, tick_seconds=0.02)
    async with line:
        line.update("Thinking…", color="cyan")
        await asyncio.sleep(0.07)
    frames = sum(1 for ch in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if ch in buf.getvalue())
    assert frames >= 2
