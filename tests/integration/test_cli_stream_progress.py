"""Integration tests for the live dashboard (CJK width, tail preview, throttle).

Uses real ``stream_query`` / ``ProgressDashboard`` / ``AnswerWriter`` with a
stubbed agent stream — no live model required. The dashboard stays in its
non-TTY zero-output mode here (captured stdout is byte-identical to before);
its state reduction is observed through the ``live_stream_runtime`` wrappers.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

pytestmark = pytest.mark.integration


def _msg_chunk(message: object) -> tuple[tuple[()], str, tuple[object, dict[str, object]]]:
    return ((), "messages", (message, {}))


@pytest.fixture
def run_fj_live_stream(
    soothe_home: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    live_stream_runtime: dict[str, Any],
) -> Any:
    from flowjet.cli import cli

    monkeypatch.setattr(cli, "configure_cli_logging", lambda **_k: None)

    def _run(argv: list[str]) -> tuple[int, str, str, dict[str, Any]]:
        code = cli.main(argv)
        captured = capsys.readouterr()
        return code, captured.out, captured.err, live_stream_runtime

    return _run


def test_cli_cjk_stream_prints_final_answer_once(
    live_stream_runtime: dict[str, Any],
    run_fj_live_stream: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = "最近一次 CI 运行（29836068180）全部绿色通过。"
    suffix = "现在创建 GitHub Release v1.0.8。"
    full = prefix + suffix
    live_stream_runtime["chunks"] = [
        _msg_chunk(AIMessageChunk(content=prefix)),
        _msg_chunk(AIMessageChunk(content=full)),
        _msg_chunk(AIMessage(content=full)),
    ]

    code, out, err, seen = run_fj_live_stream(["check", "release"])
    assert code == 0, err
    assert full + "\n" in out
    assert out.endswith(" · fj-stream-stub\n")
    assert out.count(full) == 1
    assert seen["tail_updates"] >= 1


def test_cli_cjk_progress_preview_shows_latest_clause(
    live_stream_runtime: dict[str, Any],
    run_fj_live_stream: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flowjet.cli.progress import _display_width, _line_budget

    monkeypatch.setenv("FJ_PROGRESS_WIDTH", "36")
    prefix = "前面说明。" * 4
    suffix = "现在创建 GitHub Release v1.0.8。"
    full = prefix + suffix
    live_stream_runtime["chunks"] = [
        _msg_chunk(AIMessageChunk(content=full)),
        _msg_chunk(AIMessage(content=full)),
    ]

    code, out, err, seen = run_fj_live_stream(["release"])
    assert code == 0, err
    previews = seen["previews"]
    assert previews
    preview = previews[-1]
    assert _display_width(preview) <= _line_budget()
    assert "Release" in preview or "v1.0.8" in preview
    assert "前面说明" not in preview
    # The dashboard is non-TTY here: no live frames are appended to stdout.
    assert full + "\n" in out


def test_cli_stream_throttles_rapid_narration_chunks(
    live_stream_runtime: dict[str, Any],
    run_fj_live_stream: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter([float(i) * 0.01 for i in range(2000)])
    monkeypatch.setattr("flowjet.cli.stream.time.monotonic", lambda: next(times))

    chunks = [_msg_chunk(AIMessageChunk(content="中" * (i + 1))) for i in range(50)]
    chunks.append(_msg_chunk(AIMessage(content="中" * 50)))
    live_stream_runtime["chunks"] = chunks

    code, _out, err, seen = run_fj_live_stream(["status"])
    assert code == 0, err
    assert seen["tail_updates"] < 50


def test_cli_no_stream_skips_live_narration_preview(
    live_stream_runtime: dict[str, Any],
    run_fj_live_stream: Any,
) -> None:
    narration = "正在分析仓库结构。"
    live_stream_runtime["chunks"] = [
        _msg_chunk(AIMessageChunk(content=narration)),
        _msg_chunk(AIMessage(content="## 分析结果\n完成。")),
    ]

    code, out, err, seen = run_fj_live_stream(["--no-stream", "analyze"])
    assert code == 0, err
    assert "## 分析结果\n完成。\n" in out
    assert out.endswith(" · fj-stream-stub\n")
    assert seen["tail_updates"] == 0
    # No live narration preview in --no-stream mode; the narration is still
    # accumulated into the final answer (pre-existing behavior).
    assert seen["previews"] == []
    assert out.startswith(narration)


def test_cli_stream_mixed_cjk_english_tool_then_answer(
    live_stream_runtime: dict[str, Any],
    run_fj_live_stream: Any,
) -> None:
    tool_msg = AIMessageChunk(
        content="",
        tool_call_chunks=[
            {
                "name": "run_command",
                "args": '{"command": "gh run list --limit 1"}',
                "id": "call_1",
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
        tool_calls=[
            {
                "name": "run_command",
                "args": {"command": "gh run list --limit 1"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    from langchain_core.messages import ToolMessage

    final = "CI 全部绿色通过，可以发布 v1.0.8。"
    live_stream_runtime["chunks"] = [
        _msg_chunk(AIMessageChunk(content="检查 CI 状态。")),
        _msg_chunk(tool_msg),
        _msg_chunk(ToolMessage(content="success", tool_call_id="call_1", name="run_command")),
        _msg_chunk(AIMessage(content=final)),
    ]

    code, out, err, seen = run_fj_live_stream(["ci", "status"])
    assert code == 0, err
    assert final + "\n" in out
    assert out.endswith(" · fj-stream-stub\n")
    assert seen["progress_updates"] >= 2
    assert seen["tail_updates"] >= 1
    # Narration reaches the CLI (ACP parity) even though a tool call follows.
    assert seen["reasoning"]
    assert any("检查 CI 状态" in text for text in seen["reasoning"])


def test_cli_narration_is_rendered_as_an_activity_row(
    live_stream_runtime: dict[str, Any],
    run_fj_live_stream: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cumulative answer text shows up as a reasoning row in Activity."""
    import flowjet.cli.stream as stream_mod
    from flowjet.cli.dashboard import build_dashboard
    from flowjet.cli.render import render_to_text

    dashboards: list[Any] = []
    original = stream_mod.ProgressDashboard

    class RecordingDashboard(original):  # type: ignore[valid-type, misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            dashboards.append(self)

    monkeypatch.setattr(stream_mod, "ProgressDashboard", RecordingDashboard)
    full = "先查一下 CI 状态。然后发布 v1.0.8。"
    live_stream_runtime["chunks"] = [
        _msg_chunk(AIMessageChunk(content="先查一下 CI 状态。")),
        _msg_chunk(AIMessageChunk(content=full)),
        _msg_chunk(AIMessage(content=full)),
    ]

    code, out, err, seen = run_fj_live_stream(["check", "release"])
    assert code == 0, err
    dash = dashboards[-1]
    rows = [item for item in dash.state.activity if item.kind == "reasoning"]
    assert rows and full in rows[-1].label
    rendered = render_to_text(
        build_dashboard(
            dash.state,
            frame="",
            width=64,
            color=False,
            height=24,
            now_mono=dash.state.started_at + 1.0,
        ),
        width=64,
        color=False,
    )
    assert "Activity" in rendered
    assert "›" in rendered
    assert "先查一下 CI 状态" in rendered
    assert out.startswith(full + "\n")  # stdout unchanged
    assert seen["reasoning"]


def test_cli_pause_freezes_paused_state_and_keeps_questions_visible(
    live_stream_runtime: dict[str, Any],
    run_fj_live_stream: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real CLI path: ask_user freezes a PAUSED snapshot, then questions below."""
    from langgraph.types import Interrupt

    import flowjet.cli.stream as stream_mod

    dashboards: list[Any] = []
    original = stream_mod.ProgressDashboard

    class RecordingDashboard(original):  # type: ignore[valid-type, misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            dashboards.append(self)

    monkeypatch.setattr(stream_mod, "ProgressDashboard", RecordingDashboard)
    value = {
        "type": "ask_user",
        "questions": [
            {
                "header": "Auth method",
                "question": "Which auth method should I use?",
                "options": [{"label": "API Key (Recommended)", "description": "Use an API key"}],
            }
        ],
    }
    live_stream_runtime["chunks"] = [
        ((), "updates", {"__interrupt__": (Interrupt(value=value, id="int-1"),)})
    ]

    code, out, err, seen = run_fj_live_stream(["choose", "auth"])
    assert code == 0, err
    assert dashboards and dashboards[-1].state.status == "PAUSED"
    assert dashboards[-1].state.elapsed_override is not None
    # Non-TTY: no live frames at all, the historical plain block is untouched.
    assert out.startswith("\n⏸ Paused for input:")
    assert "Which auth method" in out
    assert "API Key (Recommended)" in out
    assert "fjf -t fj-stream-stub" in out
    assert "✓ Done" not in out
    assert seen["progress_updates"] >= 1
