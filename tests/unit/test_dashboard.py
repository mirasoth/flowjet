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


def test_update_reduces_state_and_records_only_completed_tools() -> None:
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
    # Bare phase updates never enter the completion log, and a completion
    # clears the in-flight action line.
    assert len(state.activity) == 1
    assert state.activity[-1].ok is True
    assert state.activity[-1].duration_ms == 42
    assert state.activity_total == 1
    assert state.in_flight_tool is None

    dash.clear_answer_preview()
    assert dash.state.answer_preview is None


def test_activity_tail_is_bounded() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    for i in range(20):
        dash.update(f"tool {i}", ok=True, duration_ms=i)
    assert len(dash.state.activity) == 8
    assert dash.state.activity[-1].label == "tool 19"
    assert "tool 0" not in [item.label for item in dash.state.activity]


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

    # Reasoning stays in the reduced state (ACP parity) but Activity lists
    # completed tool calls only.
    out = _render(dash.state)
    assert "›" not in out
    assert "Let me check the file" not in out
    assert "The file shows a bug" not in out
    assert "✓ read_file · cli.py" in out


def test_add_reasoning_survives_the_answer_preview_reset() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.add_reasoning("Let me look that up.")
    dash.set_answer_preview("Let me look that up.")
    dash.clear_answer_preview()
    assert dash.state.answer_preview is None
    assert dash.state.activity[-1].label == "Let me look that up."
    assert "›" not in _render(dash.state)


def test_update_tool_activity_grows_one_action_line_for_partial_chunks() -> None:
    """Partial tool-arg chunks grow the action line, never an Activity row."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    # ToolStarted → the complete label starts the action line.
    dash.update("run_command", color="yellow")
    dash.set_in_flight_tool("run_command", color="yellow")
    assert dash.state.activity == []
    assert dash.state.in_flight_tool == "run_command"

    # Partial args stream in as growing labels — every chunk refreshes the SAME
    # action line (the command is still incomplete, so it stays out of Activity).
    dash.update_tool_activity("run_command sleep", color="yellow")
    dash.update_tool_activity("run_command sleep 180", color="yellow")
    dash.update_tool_activity("run_command sleep 180 && echo done", color="yellow")
    assert dash.state.in_flight_tool == "run_command sleep 180 && echo done"
    assert dash.state.phase == "run_command sleep 180 && echo done"
    assert dash.state.activity == []

    out = _render(dash.state)
    lines = out.splitlines()
    meta_idx = next(i for i, line in enumerate(lines) if "Elapsed" in line)
    assert "run_command sleep 180 && echo done" in lines[meta_idx + 1]
    assert "Activity" not in out

    # ToolCompleted → one ✓ row in Activity and the action line is cleared.
    dash.update(
        "run_command sleep 180 && echo done",
        color="green",
        ok=True,
        duration_ms=500,
    )
    assert dash.state.in_flight_tool is None
    assert len(dash.state.activity) == 1
    assert dash.state.activity[-1].ok is True
    assert dash.state.activity[-1].duration_ms == 500
    assert "✓ run_command sleep 180 && echo done" in _render(dash.state)


def test_in_flight_tool_survives_unrelated_phase_updates() -> None:
    """Generic progress events must not hide the tool call being executed."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.set_in_flight_tool("run_command git commi", color="yellow")
    dash.update("Thinking", color="cyan")
    assert dash.state.in_flight_tool == "run_command git commi"
    lines = _render(dash.state).splitlines()
    meta_idx = next(i for i, line in enumerate(lines) if "Elapsed" in line)
    assert "run_command git commi" in lines[meta_idx + 1]
    assert "Activity" not in "\n".join(lines)


def test_update_tool_activity_appends_when_no_in_flight_row() -> None:
    """A partial chunk works even when no ToolStarted update came first."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.update_tool_activity("run_command sleep 180", color="yellow")
    assert dash.state.in_flight_tool == "run_command sleep 180"
    assert dash.state.activity == []


def test_update_tool_activity_leaves_reasoning_row_alone() -> None:
    """A reasoning row at the tail must not be mutated by a partial chunk."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.add_reasoning("Let me run a command")
    dash.update_tool_activity("run_command sleep 180", color="yellow")
    assert len(dash.state.activity) == 1
    assert dash.state.activity[0].kind == "reasoning"
    assert dash.state.in_flight_tool == "run_command sleep 180"


def test_tool_result_metadata_belongs_to_a_new_completed_row() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.add_reasoning("thinking")
    dash.update("Working", color="cyan", ok=True, duration_ms=7)
    assert len(dash.state.activity) == 2
    reasoning = dash.state.activity[0]
    assert reasoning.kind == "reasoning"
    assert reasoning.ok is None and reasoning.duration_ms is None
    row = dash.state.activity[-1]
    assert row.kind == "event" and row.ok is True and row.duration_ms == 7


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
        activity=[
            Activity("Thinking", ok=True),
            Activity("Reading · cli.py", ok=True, duration_ms=42),
        ],
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
    assert "Activity (2)" in out and "Thinking" in out and "42ms" in out


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
            Activity("Running deploy_ecs/config.py", ok=True),
            Activity(phase, kind="reasoning"),
        ],
    )
    out = _render(state)
    assert "● LIVE" in out
    assert "Stage" not in out
    assert out.count(phase) == 1  # only in the main action line
    assert "✓ Running deploy_ecs/config.py" in out
    assert "›" not in out  # reasoning rows are not Activity rows


def test_build_dashboard_drops_in_flight_and_reasoning_rows_wherever_they_sit() -> None:
    """Activity shows only completed tool calls; mirrors and reasoning go."""
    phase = "grep def main"
    state = DashboardState(
        phase=phase,
        started_at=100.0,
        updated_at=time.time(),
        activity=[
            Activity("Reading Users/xiaming", ok=True, duration_ms=7),
            Activity(phase),  # in-flight phase mirror
            Activity("I will analyze the project architecture.", kind="reasoning"),
        ],
    )
    out = _render(state)
    assert out.count(phase) == 1  # only the main action line
    assert "✓ Reading Users/xiaming" in out
    assert "›" not in out


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
        activity=[Activity(f"activity-{i}", ok=True) for i in range(8)],
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
    assert captured["auto_refresh"] is True
    assert captured["vertical_overflow"] == "visible"
    assert captured["redirect_stdout"] is True
    assert captured["redirect_stderr"] is True


def test_snapshot_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    import rich.live

    from flowjet.cli.dashboard import _default_live

    monkeypatch.delenv("FJ_SNAPSHOT", raising=False)
    captured: dict[str, Any] = {}

    class Recorder:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(rich.live, "Live", Recorder)
    _default_live(console=object(), get_renderable=lambda: None, refresh_per_second=8.0)
    assert captured["transient"] is True


def test_snapshot_enabled_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import rich.live

    from flowjet.cli.dashboard import _default_live

    captured: dict[str, Any] = {}

    class Recorder:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(rich.live, "Live", Recorder)
    for val in ("1", "true", "yes"):
        monkeypatch.setenv("FJ_SNAPSHOT", val)
        captured.clear()
        _default_live(console=object(), get_renderable=lambda: None, refresh_per_second=8.0)
        assert captured["transient"] is False


def test_snapshot_disabled_on_unrecognised_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import rich.live

    from flowjet.cli.dashboard import _default_live

    captured: dict[str, Any] = {}

    class Recorder:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(rich.live, "Live", Recorder)
    for val in ("", "0", "false", "no", "off", "garbage"):
        monkeypatch.setenv("FJ_SNAPSHOT", val)
        captured.clear()
        _default_live(console=object(), get_renderable=lambda: None, refresh_per_second=8.0)
        assert captured["transient"] is True


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
# Activity = completed tool calls only; in-flight calls live on the action line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("at", [108.0, 106.0])
def test_in_flight_tool_rows_never_appear_in_activity(at: float) -> None:
    """A ``·`` row is never an Activity row, however long it has been visible."""
    state = DashboardState(
        phase="grep def main",
        started_at=100.0,
        updated_at=time.time(),
        activity=[Activity("run_command sleep 180", at=at)],
    )
    out = _render(state)
    assert "· run_command sleep 180" not in out
    assert "run_command sleep 180" not in out
    assert "Activity" not in out


def test_completed_tool_appends_exactly_one_row() -> None:
    """ToolStarted/partial chunks never log; the completion logs one ✓ row."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.update("run_command", color="yellow")
    dash.set_in_flight_tool("run_command", color="yellow")
    dash.update_tool_activity("run_command sleep", color="yellow")
    assert dash.state.activity == []
    assert dash.state.in_flight_tool == "run_command sleep"

    dash.update("run_command sleep 180 && echo done", color="green", ok=True, duration_ms=500)
    assert len(dash.state.activity) == 1
    assert dash.state.activity[-1].label == "run_command sleep 180 && echo done"
    assert dash.state.activity[-1].ok is True
    assert dash.state.activity[-1].duration_ms == 500
    assert dash.state.in_flight_tool is None
    assert "Activity" in _render(dash.state)


def test_each_completed_tool_gets_its_own_row() -> None:
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.update("read_file", color="yellow")
    dash.set_in_flight_tool("read_file", color="yellow")
    dash.update("read_file cli.py", color="green", ok=True, duration_ms=10)
    dash.update("run_command ls", color="yellow")
    dash.set_in_flight_tool("run_command ls", color="yellow")
    dash.update("run_command ls", color="green", ok=True, duration_ms=12)
    assert len(dash.state.activity) == 2
    assert [row.label for row in dash.state.activity] == ["read_file cli.py", "run_command ls"]
    assert all(row.ok is True for row in dash.state.activity)
    assert dash.state.in_flight_tool is None


def test_reasoning_rows_do_not_evict_completed_tool_rows() -> None:
    """A burst of narration must not push ✓ rows out of the completion log."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    dash.update("run_command git status", ok=True, duration_ms=9)
    for i in range(12):
        dash.add_reasoning(f"thought {i}")
    assert len([row for row in dash.state.activity if row.ok is not None]) == 1
    assert "✓ run_command git status" in _render(dash.state)


def test_activity_heading_counts_every_completed_call() -> None:
    """The heading shows the run total even though the log keeps only 8 rows."""
    dash = ProgressDashboard(io.StringIO(), enabled=True)
    for i in range(12):
        dash.update(f"tool {i}", ok=True, duration_ms=i)
    assert dash.state.activity_total == 12
    assert len(dash.state.activity) == 8
    out = _render(dash.state)
    assert "Activity (12)" in out
    assert "✓ tool 11" in out  # recent tail
    assert "✓ tool 0" not in out  # evicted from the rolling log


def test_failed_tool_is_still_a_completed_activity_row() -> None:
    state = DashboardState(
        phase="Working",
        started_at=100.0,
        updated_at=time.time(),
        activity=[Activity("run_command false", ok=False, duration_ms=3)],
    )
    out = _render(state)
    assert "✗ run_command false" in out
    assert "3ms" in out
