"""Tests for ephemeral progress formatting."""

from __future__ import annotations

import asyncio
from io import StringIO

import pytest

from fj_ai.progress import (
    ProgressLine,
    format_args_preview,
    format_tool_activity,
    format_tool_done,
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


def test_format_tool_done_error_includes_detail() -> None:
    label, color = format_tool_done(
        "wizsearch_search",
        {"query": "fj-ai"},
        is_error=True,
        detail="unexpected argument 'limit'",
    )
    assert color == "red"
    assert "Failed" in label
    assert "limit" in label


def test_progress_respects_width_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from fj_ai.progress import _display_width

    monkeypatch.setenv("FJ_PROGRESS_WIDTH", "40")
    long_path = "/Users/chenxm/Workspace/fj-ai/src/fj_ai/" + ("very_long_dir/" * 8) + "cli.py"
    label, _color = format_tool_activity("read_file", {"file_path": long_path})
    assert _display_width(label) <= 40
    assert label.startswith("Reading ")
    assert "cli.py" in label  # basename preserved


def test_truncate_path_keeps_basename() -> None:
    from fj_ai.progress import _display_width, _truncate_path

    out = _truncate_path("/a/b/c/d/e/f/g/important.py", 18)
    assert out.endswith("important.py") or "important.py" in out
    assert _display_width(out) <= 18


def test_display_width_counts_cjk_double() -> None:
    from fj_ai.progress import _display_width, _truncate_cols

    text = "中文测试"
    assert _display_width(text) == 8
    assert _truncate_cols(text, 6, tail=False) == "中文…"
    assert _truncate_cols(text, 6, tail=True) == "…测试"


def test_fit_tail_shows_latest_narration() -> None:
    from fj_ai.progress import _display_width, _fit

    long = "前面很长的一段说明。" + "现在创建 GitHub Release v1.0.8。"
    fitted = _fit(long, budget=20, tail=True)
    assert _display_width(fitted) <= 20
    assert "Release" in fitted or "v1.0.8" in fitted
    assert "前面" not in fitted


def test_truncate_cols_mixed_ascii_cjk() -> None:
    from fj_ai.progress import _display_width, _truncate_cols

    text = "CI 全部绿色通过"
    assert _display_width(text) == 15
    out = _truncate_cols(text, 10, tail=True)
    assert _display_width(out) <= 10
    assert "通过" in out


def test_progress_line_update_tail_prefers_latest_clause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fj_ai.progress import _display_width, _line_budget

    monkeypatch.setenv("FJ_PROGRESS_WIDTH", "24")
    buf = StringIO()
    line = ProgressLine(buf, enabled=True)
    long = "前面很长说明。现在创建 GitHub Release v1.0.8。"
    line.update(long, color="green", tail=True)
    rendered = buf.getvalue()
    assert "\r" in rendered
    plain = rendered.split("\r")[-1].replace("\033[2K", "")
    for code in ("\033[0m", "\033[1m", "\033[32m"):
        plain = plain.replace(code, "")
    plain = plain.lstrip("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ ").strip()
    assert _display_width(plain) <= _line_budget()
    assert "Release" in plain or "v1.0.8" in plain
    assert "前面" not in plain


def test_progress_line_cjk_paint_respects_display_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fj_ai.progress import _display_width, _line_budget

    monkeypatch.setenv("FJ_PROGRESS_WIDTH", "24")
    buf = StringIO()
    line = ProgressLine(buf, enabled=True)
    line.update("中" * 20, color="cyan")
    plain = buf.getvalue().split("\r")[-1].replace("\033[2K", "")
    for esc in ("\033[0m", "\033[1m", "\033[36m"):
        plain = plain.replace(esc, "")
    plain = plain.lstrip("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ ").strip()
    assert _display_width(plain) <= _line_budget()


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
async def test_progress_line_release_skips_clear_on_stop() -> None:
    buf = StringIO()
    line = ProgressLine(buf, enabled=True, tick_seconds=0.05)
    async with line:
        line.update("Thinking…", color="cyan")
        line.release()
        before = buf.getvalue()
        buf.write("Hello answer")
    # stop() must not erase the answer with another clear sequence after it.
    assert buf.getvalue() == before + "Hello answer"


@pytest.mark.asyncio
async def test_progress_line_spins_between_updates() -> None:
    buf = StringIO()
    line = ProgressLine(buf, enabled=True, tick_seconds=0.02)
    async with line:
        line.update("Thinking…", color="cyan")
        await asyncio.sleep(0.07)
    frames = sum(1 for ch in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if ch in buf.getvalue())
    assert frames >= 2


def test_friendly_skill_and_error_events() -> None:
    label, color = friendly_progress({"type": "soothe.skill.invoke.started", "skill": "docs"})
    assert "skill" in label.lower()
    assert "docs" in label
    assert color == "blue"

    label, color = friendly_progress({"type": "soothe.error.failed", "error": "boom"})
    assert "Error" in label
    assert "boom" in label
    assert color == "red"


def test_friendly_cognition_variants() -> None:
    assert friendly_progress({"type": "soothe.cognition.plan.started"})[0] == "Planning…"
    label, color = friendly_progress({"type": "soothe.cognition.goal.completed"})
    assert label == "Goal complete"
    assert color == "green"
    label, _ = friendly_progress(
        {"type": "soothe.cognition.intent.classified", "intent": "refactor auth"}
    )
    assert "Understanding" in label
    assert "refactor" in label


def test_friendly_tool_failed_event() -> None:
    label, color = friendly_progress(
        {
            "type": "soothe.tool.invocation.failed",
            "tool": "run_command",
            "command": "false",
        }
    )
    assert color == "red"
    assert "Failed" in label


def test_friendly_skips_output_and_empty() -> None:
    assert friendly_progress({"type": "soothe.output.token"}) is None
    assert friendly_progress({"type": ""}) is None
    assert friendly_progress("not-a-dict") is None  # type: ignore[arg-type]


def test_normalize_args_variants() -> None:
    from fj_ai.progress import _normalize_args

    assert _normalize_args(None) == {}
    assert _normalize_args("") == {}
    assert _normalize_args('{"file_path": "a.py"}') == {"file_path": "a.py"}
    assert _normalize_args("not-json") == {"_text": "not-json"}
    assert _normalize_args(["x"]) == {"_text": "x"}
    nested = _normalize_args({"value": '{"path": "b.py"}', "extra": 1})
    assert nested["path"] == "b.py"
    assert nested["extra"] == 1


def test_compact_types() -> None:
    from fj_ai.progress import _compact

    assert _compact(None) == ""
    assert _compact(True) == "true"
    assert _compact(False) == "false"
    assert _compact(3) == "3"
    assert _compact(["a", "b", "c", "d", "e", "f"]) == "a, b, c, d, e, …"
    assert _compact([]) == "[]"
    assert '{"k"' in _compact({"k": 1})


def test_color_enabled_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from fj_ai.progress import _color_enabled

    stream = StringIO()
    monkeypatch.setenv("NO_COLOR", "1")
    assert _color_enabled(stream) is False
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FJ_FORCE_COLOR", "1")
    assert _color_enabled(stream) is True


def test_line_budget_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from fj_ai.progress import _line_budget

    monkeypatch.setenv("FJ_PROGRESS_WIDTH", "50")
    assert _line_budget() == 50


def test_format_edit_file_preview() -> None:
    preview = format_args_preview(
        "edit_file",
        {"file_path": "a.py", "old_string": "foo", "new_string": "bar"},
        max_parts=3,
    )
    assert "a.py" in preview or "replace" in preview or "→" in preview


def test_format_tool_activity_unknown_tool() -> None:
    label, color = format_tool_activity("custom_tool", {"query": "x"})
    assert "Running" in label or "custom" in label.lower()
    assert color == "yellow"
    label, _ = format_tool_activity("read_file", None)
    assert label.startswith("Reading")


def test_progress_line_release_is_idempotent() -> None:
    buf = StringIO()
    line = ProgressLine(buf, enabled=True)
    line.update("Thinking…", color="cyan")
    line.release()
    before = buf.getvalue()
    line.release()
    assert buf.getvalue() == before
    line.clear()
    assert buf.getvalue() == before
