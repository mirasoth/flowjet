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
    assert "Stage" in out and "Reading · cli.py" in out
    assert "Step" in out and "2 / 5" in out
    assert "Tool" in out and "read_file" in out
    assert "Elapsed" in out and "12s" in out
    assert "Tokens" in out and "12.3K" in out
    assert "Updated" in out
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
