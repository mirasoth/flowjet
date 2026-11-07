"""Unit tests for the multi-line ``ProgressDashboard`` renderer."""

from __future__ import annotations

import asyncio
import io
import re
import time
from typing import Any

import pytest

from flowjet.cli.dashboard import (
    Activity,
    DashboardState,
    ProgressDashboard,
    _duration,
    _tail_limit,
    _tokens,
    build_dashboard,
)
from flowjet.cli.render import render_to_text, terminal_metrics

_ANSI_RE = re.compile(r"\033\[[0-9;?]*[ -/]*[@-~]")


class TTYBuffer(io.StringIO):
    """StringIO that claims to be a terminal (drives the rich code path)."""

    def isatty(self) -> bool:
        return True


class FakeLive:
    """Records the Live lifecycle without touching a real terminal."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.console = kwargs["console"]
        self.started = False
        self.stopped = False
        self.refresh_count = 0

    def start(self, refresh: bool = False) -> None:
        self.started = True

    def refresh(self) -> None:
        self.refresh_count += 1
        self.kwargs["get_renderable"]()

    def stop(self) -> None:
        self.stopped = True


def _render(
    state: DashboardState,
    *,
    frame: str = "⠋",
    width: int = 72,
    color: bool = False,
    height: int = 24,
) -> str:
    return render_to_text(
        build_dashboard(
            state,
            frame=frame,
            width=width,
            color=color,
            height=height,
            now_mono=state.started_at + 12.0,
        ),
        width=width,
        color=color,
    )


# ---------------------------------------------------------------------------
# Pure helpers / state reduction
# ---------------------------------------------------------------------------


def test_duration_and_tokens() -> None:
    assert _duration(0.4) == "0s"
    assert _duration(42) == "42s"
    assert _duration(95) == "1m35s"
    assert _duration(3700) == "1h01m"
    assert _tokens(None) == "—"
    assert _tokens(842) == "842"
    assert _tokens(12_500) == "12.5K"
    assert _tokens(3_400_000) == "3.4M"


def test_tail_limit_shrinks_on_short_terminals() -> None:
    assert _tail_limit(24) == 6
    assert _tail_limit(18) == 4
    assert _tail_limit(12) == 2


def test_update_reduces_state_and_deduplicates_activity() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.update("Thinking", color="cyan")
    dash.update("Thinking", color="cyan")
    dash.update("Reading · cli.py", color="yellow", ok=True, duration_ms=42)
    dash.set_step(2, 5)
    dash.set_tool("read_file", "path=cli.py")
    dash.set_tokens(12345)
    dash.add_failure()
    dash.set_answer_preview("draft answer")

    state = dash.state
    assert state.phase == "Reading · cli.py"
    assert state.color == "yellow"
    assert state.step == 2 and state.steps == 5
    assert state.current_tool == "read_file"
    assert state.tool_args_preview == "path=cli.py"
    assert state.total_tokens == 12345
    assert state.failed_tools == 1
    assert state.answer_preview == "draft answer"
    assert len(state.activity) == 2
    assert state.activity[-1].ok is True
    assert state.activity[-1].duration_ms == 42

    dash.clear_answer_preview()
    assert dash.state.answer_preview is None


def test_activity_tail_is_bounded() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    for i in range(20):
        dash.update(f"step {i}")
    assert len(dash.state.activity) == 8
    assert dash.state.activity[-1].label == "step 19"
    assert "step 0" not in [item.label for item in dash.state.activity]


def test_control_characters_are_stripped_from_panel_text() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.update("Injected \x1b[31mred\x1b[0m\r\nsecond line")
    assert "\x1b" not in dash.state.phase
    assert "\r" not in dash.state.phase
    assert "\n" not in dash.state.phase
    out = _render(dash.state)
    assert "\x1b" not in out


def test_add_reasoning_keeps_one_row_per_stretch_and_interleaves_tools() -> None:
    """Cumulative Narration updates one row; tool calls start a new stretch."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.add_reasoning("Let me check")
    dash.add_reasoning("Let me check the file")
    assert len(dash.state.activity) == 1
    assert dash.state.activity[-1].kind == "reasoning"
    assert dash.state.activity[-1].label == "Let me check the file"

    dash.update("read_file · cli.py", color="yellow", ok=True, duration_ms=12)
    dash.add_reasoning("The file shows a bug")
    assert [item.kind for item in dash.state.activity] == ["reasoning", "event", "reasoning"]
    assert dash.state.activity[0].label == "Let me check the file"
    assert dash.state.activity[-1].label == "The file shows a bug"

    out = _render(dash.state)
    assert "› Let me check the file" in out
    assert "› The file shows a bug" in out
    assert "✓ read_file · cli.py" in out


def test_add_reasoning_survives_the_answer_preview_reset() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.add_reasoning("Let me look that up.")
    dash.set_answer_preview("Let me look that up.")
    dash.clear_answer_preview()
    assert dash.state.answer_preview is None
    assert dash.state.activity[-1].label == "Let me look that up."
    assert "› Let me look that up." in _render(dash.state)


def test_update_tool_activity_grows_one_row_for_partial_chunks() -> None:
    """Partial tool-arg chunks update the in-flight row, not one row per chunk."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    # ToolStarted → first row (args empty, label is just the tool verb).
    dash.update("run_command", color="yellow")
    assert len(dash.state.activity) == 1

    # Partial args stream in as growing labels — each must update the SAME row.
    dash.update_tool_activity("run_command sleep", color="yellow")
    dash.update_tool_activity("run_command sleep 180", color="yellow")
    dash.update_tool_activity("run_command sleep 180 && echo done", color="yellow")
    assert len(dash.state.activity) == 1
    assert dash.state.activity[-1].label == "run_command sleep 180 && echo done"
    assert dash.state.phase == "run_command sleep 180 && echo done"

    # ToolCompleted with the same label → updates the in-flight row in place
    # with ok/duration (the · becomes ✓), not a duplicate row.
    dash.update(
        "run_command sleep 180 && echo done",
        color="green",
        ok=True,
        duration_ms=500,
    )
    assert len(dash.state.activity) == 1
    assert dash.state.activity[-1].ok is True
    assert dash.state.activity[-1].duration_ms == 500


def test_update_tool_activity_appends_when_no_in_flight_row() -> None:
    """If there is no in-flight event row yet, create one rather than crashing."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.update_tool_activity("run_command sleep 180", color="yellow")
    assert len(dash.state.activity) == 1
    assert dash.state.activity[-1].label == "run_command sleep 180"


def test_update_tool_activity_appends_after_reasoning() -> None:
    """A reasoning row at the tail must not be mutated; a new event row starts."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.add_reasoning("Let me run a command")
    dash.update_tool_activity("run_command sleep 180", color="yellow")
    assert len(dash.state.activity) == 2
    assert dash.state.activity[0].kind == "reasoning"
    assert dash.state.activity[1].kind == "event"
    assert dash.state.activity[1].label == "run_command sleep 180"


def test_tool_result_metadata_does_not_attach_to_a_reasoning_row() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.add_reasoning("thinking")
    # Same phase label → ``update`` takes its dedup branch; tool metadata must
    # not be written onto the reasoning row that happens to be last.
    dash.update("Working", color="cyan", ok=True, duration_ms=7)
    row = dash.state.activity[-1]
    assert row.kind == "reasoning"
    assert row.ok is None and row.duration_ms is None


def test_add_reasoning_is_cleaned_width_bounded_and_silent_on_non_tty() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.add_reasoning("Injected \x1b[31mred\x1b[0m\r\n" + "长" * 200)
    label = dash.state.activity[-1].label
    assert "\x1b" not in label and "\r" not in label and "\n" not in label
    assert len(label) <= 60
    assert "\x1b" not in _render(dash.state)

    out = io.StringIO()
    quiet = ProgressDashboard(out)
    quiet.add_reasoning("thinking")
    assert out.getvalue() == ""
    assert quiet.state.activity[-1].kind == "reasoning"


# ---------------------------------------------------------------------------
# Pure rendering
# ---------------------------------------------------------------------------


def test_build_dashboard_renders_multi_line_summary() -> None:
    state = DashboardState(
        phase="Reading · cli.py",
        status="LIVE",
        step=2,
        steps=5,
        current_tool="read_file",
        tool_args_preview="path=cli.py",
        total_tokens=12345,
        started_at=100.0,
        updated_at=time.time(),
        activity=[Activity("Thinking", ok=True), Activity("Reading · cli.py", duration_ms=42)],
    )
    out = _render(state)
    assert len(out.splitlines()) > 8  # a real multi-line region, not one status line
    assert "LIVE" in out
    assert "FlowJet Agent" in out
    assert "Stage" not in out and "Reading · cli.py" in out
    assert "Step" in out and "2 / 5" in out
    # The duplicate Tool row, the Stage label gutter and the heading's copy
    # are gone; only the main line and the *completed* history row carry it.
    assert "Tool" not in out and "read_file" not in out
    assert "● LIVE  Reading" not in out
    assert out.count("Reading · cli.py") == 2
    assert "Elapsed" in out and "12s" in out
    assert "Tokens" in out and "12.3K" in out
    assert "Updated" in out
    # Step/Elapsed/Tokens/Updated share ONE meta line, not four label rows.
    meta = [line for line in out.splitlines() if "Elapsed" in line]
    assert len(meta) == 1
    assert "Step" in meta[0] and "Tokens" in meta[0] and "Updated" in meta[0]
    assert "Activity" in out and "Thinking" in out and "42ms" in out


@pytest.mark.parametrize(
    ("status", "badge"),
    [("LIVE", "● LIVE"), ("DONE", "✓ DONE"), ("FAILED", "✗ FAILED"), ("PAUSED", "⏸ PAUSED")],
)
def test_build_dashboard_status_badges(status: str, badge: str) -> None:
    state = DashboardState(phase="Working", status=status, started_at=100.0, updated_at=time.time())
    out = _render(state, frame="" if status != "LIVE" else "⠋")
    assert badge in out
    if status != "LIVE":
        assert "⠋" not in out


def test_build_dashboard_meta_row_omits_empty_values() -> None:
    """Screenshot case: Step — and Tokens — must not occupy two rows."""
    state = DashboardState(
        phase="ls mirasoth/flowjet",
        status="LIVE",
        started_at=100.0,
        updated_at=time.time(),
    )
    out = _render(state)
    assert "—" not in out
    meta = [line for line in out.splitlines() if "Elapsed" in line]
    assert len(meta) == 1
    assert "Updated" in meta[0]
    assert "Step" not in meta[0] and "Tokens" not in meta[0]
    assert out.count("ls mirasoth/flowjet") == 1


def test_build_dashboard_meta_row_stays_one_line_on_narrow_terminals() -> None:
    state = DashboardState(
        phase="Thinking",
        step=2,
        steps=5,
        total_tokens=12345,
        started_at=100.0,
        updated_at=time.time(),
    )
    out = _render(state, width=36)
    assert len([line for line in out.splitlines() if "2 / 5" in line]) == 1


def test_build_dashboard_stage_sits_below_meta_and_is_left_aligned() -> None:
    """Meta line first; the action line follows, starting at the same column."""
    state = DashboardState(
        phase="grep def main in cli/cli.py",
        status="LIVE",
        step=1,
        steps=6,
        started_at=100.0,
        updated_at=time.time(),
    )
    lines = _render(state).splitlines()
    meta_idx = next(i for i, line in enumerate(lines) if "Updated" in line)
    stage_idx = next(i for i, line in enumerate(lines) if "grep def main" in line)
    assert stage_idx == meta_idx + 1
    assert lines[stage_idx].index("grep") == lines[meta_idx].index("Step")
    assert "Stage" not in _render(state)


def test_build_dashboard_does_not_repeat_the_current_stage() -> None:
    """Heading / main line / Activity must not all print the in-flight command."""
    phase = "run_command find tests"
    state = DashboardState(
        phase=phase,
        status="LIVE",
        started_at=100.0,
        updated_at=time.time(),
        activity=[
            Activity("Running deploy_ecs/config.py"),
            Activity(phase, kind="reasoning"),
        ],
    )
    out = _render(state)
    assert "● LIVE" in out
    assert "Stage" not in out
    assert out.count(phase) == 1  # only in the main action line
    assert "Running deploy_ecs/config.py" in out  # history is preserved
    assert "›" not in out  # trailing mirror of the current stage is dropped


def test_build_dashboard_drops_the_phase_mirror_wherever_it_sits() -> None:
    """A reasoning row can leave the in-flight mirror mid-tail; it must go."""
    phase = "grep def main"
    state = DashboardState(
        phase=phase,
        started_at=100.0,
        updated_at=time.time(),
        activity=[
            Activity("Reading Users/xiaming"),
            Activity(phase),
            Activity("I will analyze the project architecture.", kind="reasoning"),
        ],
    )
    out = _render(state)
    assert out.count(phase) == 1  # only the main action line
    assert "Reading Users/xiaming" in out
    assert "›" in out  # reasoning history is preserved


def test_build_dashboard_keeps_completed_rows_sharing_the_stage_label() -> None:
    state = DashboardState(
        phase="Reading · cli.py",
        started_at=100.0,
        updated_at=time.time(),
        activity=[Activity("Reading · cli.py", ok=True, duration_ms=42)],
    )
    out = _render(state)
    assert "42ms" in out
    assert "✓" in out


def test_build_dashboard_shows_failed_tool_count_only_when_nonzero() -> None:
    state = DashboardState(phase="Working", started_at=100.0, updated_at=time.time())
    assert "Failed tools" not in _render(state)
    state.failed_tools = 2
    assert "Failed tools" in _render(state)


def test_build_dashboard_limits_tail_by_terminal_height() -> None:
    state = DashboardState(
        phase="Working",
        started_at=100.0,
        updated_at=time.time(),
        activity=[Activity(f"activity-{i}") for i in range(8)],
    )
    tall = _render(state, height=24)
    short = _render(state, height=15)
    assert "activity-0" not in tall
    assert "activity-7" in tall
    assert "activity-5" in tall
    assert "activity-5" not in short
    assert "activity-7" in short
    assert "activity-6" in short


def test_build_dashboard_colour_switch_removes_ansi() -> None:
    state = DashboardState(phase="Working", started_at=100.0, updated_at=time.time())
    assert not _ANSI_RE.search(_render(state, color=False))
    assert _ANSI_RE.search(_render(state, color=True))


def test_terminal_metrics_honours_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FJ_PROGRESS_WIDTH", "60")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FJ_FORCE_COLOR", raising=False)
    width, height, color = terminal_metrics(TTYBuffer())
    assert width == 60
    assert height >= 8
    assert color is True

    monkeypatch.setenv("NO_COLOR", "1")
    assert terminal_metrics(TTYBuffer())[2] is False
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("FJ_FORCE_COLOR", "yes")
    assert terminal_metrics(io.StringIO())[2] is True


# ---------------------------------------------------------------------------
# Live lifecycle / TTY gate / snapshot
# ---------------------------------------------------------------------------


def test_non_tty_is_silent_but_still_reduces_state() -> None:
    out = io.StringIO()
    err = io.StringIO()
    dash = ProgressDashboard(out)
    assert not dash.enabled
    asyncio.run(dash.start())
    dash.update("Thinking")
    dash.set_step(1, 3)
    dash.set_tokens(123)
    dash.blank()
    dash.write_through("  [verbose] line\n", err)
    dash.repaint()
    dash.finalize("DONE")

    assert out.getvalue() == ""
    assert err.getvalue() == "  [verbose] line\n"
    assert dash.state.phase == "Thinking"
    assert dash.state.step == 1
    assert dash.state.total_tokens == 123
    assert dash.state.status == "DONE"


def test_finalize_refreshes_stops_and_is_idempotent() -> None:
    created: list[FakeLive] = []

    def factory(**kwargs: Any) -> FakeLive:
        live = FakeLive(**kwargs)
        created.append(live)
        return live

    dash = ProgressDashboard(TTYBuffer(), enabled=True, live_factory=factory)
    asyncio.run(dash.start())
    dash.update("Working")
    live = created[0]
    assert live.started and not live.stopped
    assert callable(live.kwargs["get_renderable"])
    assert live.kwargs["console"] is not None

    dash.finalize("DONE", duration_s=9.0, tokens=99)
    assert live.stopped
    assert live.refresh_count >= 1
    assert dash.state.status == "DONE"
    assert dash.state.elapsed_override == 9.0
    assert dash.state.total_tokens == 99

    # ``__aexit__`` calls stop("FAILED") on error paths; an already finalized
    # PAUSED/DONE snapshot must never be overwritten or erased.
    asyncio.run(dash.stop("FAILED"))
    assert dash.state.status == "DONE"


async def test_async_context_manager_marks_failed_on_exception() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    with pytest.raises(ValueError, match="boom"):
        async with dash:
            raise ValueError("boom")
    assert dash.state.status == "FAILED"


async def test_async_context_manager_marks_done_on_success() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    async with dash:
        dash.update("Working")
    assert dash.state.status == "DONE"


def test_broken_live_factory_degrades_without_output() -> None:
    def broken(**_kwargs: Any) -> Any:
        raise RuntimeError("rich unavailable")

    buf = TTYBuffer()
    dash = ProgressDashboard(buf, enabled=True, live_factory=broken)
    asyncio.run(dash.start())
    dash.update("Still running")
    dash.finalize("DONE")
    assert buf.getvalue() == ""
    assert dash.state.phase == "Still running"
    assert dash.state.status == "DONE"


def test_default_live_keeps_snapshot_and_auto_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    import rich.live

    from flowjet.cli.dashboard import _default_live

    captured: dict[str, Any] = {}

    class Recorder:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(rich.live, "Live", Recorder)
    _default_live(console=object(), get_renderable=lambda: None, refresh_per_second=8.0)
    assert captured["transient"] is False
    assert captured["auto_refresh"] is True
    assert captured["vertical_overflow"] == "visible"
    assert captured["redirect_stdout"] is True
    assert captured["redirect_stderr"] is True


def test_write_through_uses_live_console_while_active() -> None:
    live = FakeLive(console=io.StringIO(), get_renderable=lambda: "x")
    printed: list[Any] = []

    class Console:
        def print(self, *args: Any, **_kwargs: Any) -> None:
            printed.append(args[0])

    live.console = Console()  # type: ignore[assignment]
    dash = ProgressDashboard(TTYBuffer(), enabled=True, live_factory=lambda **_k: live)
    asyncio.run(dash.start())
    target = io.StringIO()
    dash.write_through("  [verbose] line\n", target)
    assert target.getvalue() == ""
    assert printed and "verbose" in str(printed[0])
    dash.finalize()


# ---------------------------------------------------------------------------
# Brief in-flight tool rows are dropped; long-running ones stay
# ---------------------------------------------------------------------------


def test_brief_in_flight_tool_row_is_dropped_from_history() -> None:
    """A ``·`` row for a quick tool call (< 5s) must not clutter the Activity tail."""
    state = DashboardState(
        phase="grep def main",  # different from the historical row
        started_at=100.0,
        updated_at=time.time(),
        activity=[
            Activity("run_command sleep 180", at=108.0),  # 4s ago → brief
        ],
    )
    out = _render(state)
    # _render uses now_mono = started_at + 12 = 112; 112 - 108 = 4 < 5 → dropped
    assert "· run_command sleep 180" not in out


def test_long_running_in_flight_tool_row_stays_in_history() -> None:
    """A ``·`` row for a command visible > 5s stays so the user sees what's slow."""
    state = DashboardState(
        phase="grep def main",  # different from the historical row
        started_at=100.0,
        updated_at=time.time(),
        activity=[
            Activity("run_command sleep 180", at=106.0),  # 6s ago → stays
        ],
    )
    out = _render(state)
    # _render uses now_mono = started_at + 12 = 112; 112 - 106 = 6 > 5 → kept
    assert "· run_command sleep 180" in out


def test_completed_tool_row_folds_into_in_flight_same_tool_row() -> None:
    """When a tool completes with a different label but same tool, fold in place."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    # ToolStarted → in-flight row (bare ``·``)
    dash.update("run_command", color="yellow")
    assert len(dash.state.activity) == 1
    assert dash.state.activity[-1].ok is None

    # ToolCompleted with a different (fuller) label — same tool ``run_command``
    dash.update("run_command sleep 180 && echo done", color="green", ok=True, duration_ms=500)
    assert len(dash.state.activity) == 1  # folded, not duplicated
    assert dash.state.activity[-1].label == "run_command sleep 180 && echo done"
    assert dash.state.activity[-1].ok is True
    assert dash.state.activity[-1].duration_ms == 500


def test_completed_tool_does_not_fold_into_different_tool_row() -> None:
    """A completion for a different tool must append, not fold."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.update("read_file", color="yellow")
    dash.update("run_command ls", color="green", ok=True, duration_ms=10)
    assert len(dash.state.activity) == 2
    assert dash.state.activity[-1].label == "run_command ls"
    assert dash.state.activity[-1].ok is True
