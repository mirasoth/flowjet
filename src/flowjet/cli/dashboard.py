"""Multi-line, in-place agent progress dashboard for the ``fj`` CLI.

The terminal renderer is split in two:

* :class:`DashboardState` is the single structured source of truth, and
  :func:`build_dashboard` is a **pure** state -> rich ``Renderable`` function
  (unit-testable on a ``StringIO`` console without any live display running).
* :class:`ProgressDashboard` owns the ``rich.live.Live`` lifecycle, the TTY
  gate, interleaved output and the final snapshot.

``Live`` itself is the only refresh source (its ``auto_refresh`` thread replaces
the old hand-rolled 0.08s asyncio spinner). ``transient=False`` leaves the last
frame on screen, which is what makes the DONE / FAILED / PAUSED snapshot visible
above the final answer.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TextIO

from flowjet.cli.render import _clean, make_console, terminal_metrics

# Spinner glyphs for the LIVE badge (the old single-line renderer is gone).
_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_DEFAULT_WIDTH = 72
_DEFAULT_HEIGHT = 24
_ACTIVITY_MAX = 8
_REFRESH_PER_SECOND = 8.0
_TAIL_MIN = 2
_TAIL_MAX = 6
# Rows taken by the panel chrome, heading, summary table and answer preview.
_CHROME_ROWS = 14
# Ceiling for a reasoning stretch before it is truncated into one panel row.
_REASONING_MAX_CHARS = 2000

_STATUS_BADGES: dict[str, tuple[str, str]] = {
    "LIVE": ("● LIVE", "cyan"),
    "DONE": ("✓ DONE", "green"),
    "FAILED": ("✗ FAILED", "red"),
    "PAUSED": ("⏸ PAUSED", "yellow"),
}


def _one_line(text: Any, limit: int) -> str:
    """Single-line, control-character-free, width-bounded panel text."""
    return _clean(text, limit=max(1, limit)).strip()


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _tokens(value: int | None) -> str:
    if value is None:
        return "—"
    if value < 1000:
        return str(value)
    if value < 1_000_000:
        return f"{value / 1000:.1f}K"
    return f"{value / 1_000_000:.1f}M"


def _clock(at: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(at))


def _tail_limit(height: int) -> int:
    """Shrink the activity tail so the panel fits short terminals."""
    return max(_TAIL_MIN, min(_TAIL_MAX, height - _CHROME_ROWS))


@dataclass
class Activity:
    """One entry in the rolling activity tail."""

    label: str
    color: str = "cyan"
    ok: bool | None = None
    duration_ms: int | None = None
    at: float = 0.0
    # ``event`` = phase/tool activity; ``reasoning`` = intermediate Narration.
    kind: str = "event"


@dataclass
class DashboardState:
    """Structured state shared by the event reducer and the renderer."""

    phase: str = "Working"
    color: str = "cyan"
    status: str = "LIVE"
    step: int | None = None
    steps: int | None = None
    current_tool: str | None = None
    tool_args_preview: str | None = None
    answer_preview: str | None = None
    total_tokens: int | None = None
    failed_tools: int = 0
    started_at: float = 0.0
    updated_at: float = 0.0
    elapsed_override: float | None = None
    activity: list[Activity] = field(default_factory=list)

    def elapsed(self, now_mono: float) -> float:
        if self.elapsed_override is not None:
            return self.elapsed_override
        return max(0.0, now_mono - self.started_at)

    def append_activity(self, item: Activity) -> None:
        self.activity.append(item)
        if len(self.activity) > _ACTIVITY_MAX:
            del self.activity[: len(self.activity) - _ACTIVITY_MAX]


def build_dashboard(
    state: DashboardState,
    *,
    frame: str,
    width: int,
    color: bool,
    height: int,
    now_mono: float,
) -> Any:  # noqa: ANN401 - rich Renderable
    """Pure renderer: turn a :class:`DashboardState` into a rich renderable.

    ``frame`` is the spinner glyph (empty for terminal states), ``width`` /
    ``height`` come from :func:`flowjet.cli.render.terminal_metrics`, and
    ``now_mono`` is injected so elapsed time is deterministic in tests.
    """
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    def style(name: str) -> str:
        return name if color else ""

    badge, badge_color = _STATUS_BADGES.get(state.status, _STATUS_BADGES["LIVE"])
    border = badge_color

    # Heading is state only. The in-flight action has exactly one home: the
    # main line below. Repeating it here (and in the activity tail) made the
    # same long command appear three times in one panel.
    heading = Text()
    if frame and state.status == "LIVE":
        heading.append(f"{frame} ", style=style("bold cyan"))
    heading.append(badge, style=style(f"bold {badge_color}"))

    step = f"{state.step} / {state.steps}" if state.step is not None and state.steps else "—"
    stage = state.phase
    if stage == "Working" and state.current_tool:
        # Fallback for backends that emit a bare phase: keep the tool detail
        # visible without duplicating the full args preview on its own row.
        stage = (
            f"{state.current_tool} · {state.tool_args_preview}"
            if state.tool_args_preview
            else state.current_tool
        )
    # Step / Elapsed / Tokens / Updated share ONE compact line instead of four
    # label rows. Empty Step and Tokens are skipped rather than printing a "—"
    # placeholder that wastes a row. Narrow terminals drop the labels.
    parts: list[tuple[str, str]] = []
    if step != "—":
        parts.append(("Step", step))
    parts.append(("Elapsed", _duration(state.elapsed(now_mono))))
    if state.total_tokens is not None:
        parts.append(("Tokens", _tokens(state.total_tokens)))
    parts.append(("Updated", _clock(state.updated_at)))
    if state.failed_tools:
        parts.append(("Failed tools", str(state.failed_tools)))
    meta_full = " · ".join(f"{key} {value}" for key, value in parts)
    meta_short = " · ".join(value for _, value in parts)
    meta_budget = max(16, width - 6)
    meta = meta_full if len(meta_full) <= meta_budget else meta_short

    # Meta first, then the in-flight action as the panel's main line. No
    # key/value table: its 12-column label gutter pushed "Thinking" far to the
    # right, out of alignment with the meta line and the Activity rows.
    blocks: list[Any] = [
        heading,
        Text(_one_line(meta, meta_budget), style=style("dim")),
        Text(_one_line(stage, meta_budget), style=style(f"bold {state.color}")),
    ]

    if state.answer_preview:
        blocks.append(Text(""))
        blocks.append(
            Text(
                f"Answer · {_one_line(state.answer_preview, width - 12)}",
                style=style("dim green"),
            )
        )

    # Activity is history, never a second copy of the main action line.
    # ``update`` appends the in-flight phase, and a later reasoning row can
    # leave that mirror in the middle of the tail, so filter by content rather
    # than by position. Completed rows (ok / timing) carry extra information
    # and stay; reasoning with different text stays.
    history = [
        item
        for item in state.activity
        if not (item.label == state.phase and item.ok is None and item.duration_ms is None)
    ]
    tail = history[-_tail_limit(height) :]
    if tail:
        blocks.append(Text(""))
        blocks.append(Text("Activity", style=style("bold dim")))
        for item in tail:
            if item.kind == "reasoning":
                # Intermediate answer/reasoning text between tool calls.
                mark = "›"
                item_style = "dim cyan"
            else:
                mark = "✓" if item.ok is True else ("✗" if item.ok is False else "·")
                item_style = "green" if item.ok else "red" if item.ok is False else item.color
            suffix = f" · {item.duration_ms}ms" if item.duration_ms is not None else ""
            blocks.append(
                Text(
                    f"{mark} {_one_line(item.label, width - 12)}{suffix}",
                    style=style(item_style),
                )
            )

    return Panel(
        Group(*blocks),
        title="FlowJet Agent",
        title_align="left",
        border_style=style(border),
        padding=(0, 1),
    )


def _default_live(
    *,
    console: Any,  # noqa: ANN401 - rich Console
    get_renderable: Callable[[], Any],
    refresh_per_second: float,
) -> Any:  # noqa: ANN401 - rich Live
    from rich.live import Live

    return Live(
        get_renderable=get_renderable,
        console=console,
        auto_refresh=True,
        refresh_per_second=refresh_per_second,
        transient=False,
        redirect_stdout=True,
        redirect_stderr=True,
        vertical_overflow="visible",
    )


class _ThroughStream:
    """Proxy a logging handler's stream through the live console.

    ``Live.redirect_stderr`` replaces ``sys.stderr`` but an already-constructed
    :class:`logging.StreamHandler` keeps pointing at the original stream, so
    ``-v`` / ``FJ_LOG_LEVEL=debug`` records would otherwise tear the panel.
    """

    def __init__(self, dashboard: ProgressDashboard, fallback: TextIO) -> None:
        self._dashboard = dashboard
        self._fallback = fallback

    def write(self, text: str) -> int:
        self._dashboard.write_through(text, self._fallback)
        return len(text)

    def flush(self) -> None:
        try:
            self._fallback.flush()
        except Exception:  # noqa: BLE001 - logging must never break a run
            pass

    def isatty(self) -> bool:
        return bool(getattr(self._fallback, "isatty", lambda: False)())

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        """Stay a transparent stream for handlers/capture probing ``getvalue`` etc."""
        return getattr(self._fallback, name)


class ProgressDashboard:
    """Fixed-region, multi-line progress display (TTY only).

    Keeps the old ``update`` / ``blank`` / ``repaint`` / async-context-manager
    contract so ``stream.py`` and its injected ``StringIO`` tests stay small.
    ``blank``/``repaint`` now suspend/resume *event-driven* refreshes instead of
    erasing a line; interleaved writers go through :meth:`write_through` so
    ``Live``'s render hook places their output outside the live region.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        enabled: bool | None = None,
        refresh_per_second: float = _REFRESH_PER_SECOND,
        live_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._stream = stream if stream is not None else sys.stdout
        if enabled is None:
            enabled = bool(getattr(self._stream, "isatty", lambda: False)())
        self._enabled = enabled
        self._refresh_per_second = refresh_per_second
        self._live_factory = live_factory or _default_live
        self._live: Any = None
        self._started = False
        self._finalized = False
        self._suspended = False
        self._frame = 0
        self._log_streams: list[tuple[logging.StreamHandler, TextIO]] = []
        self._state = DashboardState(started_at=time.monotonic(), updated_at=time.time())
        # Raw text of the reasoning stretch currently shown as one tail row.
        self._last_reasoning = ""
        self._width = _DEFAULT_WIDTH
        self._height = _DEFAULT_HEIGHT
        self._color = False
        if self._enabled:
            try:
                self._width, self._height, self._color = terminal_metrics(self._stream)
            except Exception:  # noqa: BLE001 - cosmetic path, never break a run
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def state(self) -> DashboardState:
        return self._state

    async def __aenter__(self) -> ProgressDashboard:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, *_exc: object) -> None:
        await self.stop("FAILED" if exc_type is not None else "DONE")

    async def start(self) -> None:
        """Start ``Live`` once; a broken rich install degrades to no display."""
        if not self._enabled or self._started or self._finalized:
            return
        try:
            console = make_console(self._stream, width=self._width, color=self._color)
            live = self._live_factory(
                console=console,
                get_renderable=self._render_frame,
                refresh_per_second=self._refresh_per_second,
            )
            live.start(refresh=True)
        except Exception:  # noqa: BLE001 - rendering must never break a run
            self._live = None
            return
        self._live = live
        self._started = True
        self._redirect_logging()

    def _redirect_logging(self) -> None:
        """Route console logging handlers through ``write_through``.

        File handlers (``FJ_LOG_FILE``) are deliberately left alone — they never
        write to the terminal and must keep full tracebacks verbatim.
        """
        for handler in logging.getLogger().handlers:
            if not isinstance(handler, logging.StreamHandler):
                continue
            if isinstance(handler, logging.FileHandler):
                continue
            stream = getattr(handler, "stream", None)
            if stream is None or isinstance(stream, _ThroughStream):
                continue
            try:
                handler.setStream(_ThroughStream(self, stream))  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001 - logging must never break a run
                continue
            self._log_streams.append((handler, stream))

    def _restore_logging(self) -> None:
        for handler, stream in self._log_streams:
            try:
                handler.setStream(stream)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001 - logging must never break a run
                pass
        self._log_streams.clear()

    def _render_frame(self) -> Any:  # noqa: ANN401 - rich Renderable
        self._frame += 1
        frame = _SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]
        return build_dashboard(
            self._state,
            frame=frame,
            width=self._width,
            color=self._color,
            height=self._height,
            now_mono=time.monotonic(),
        )

    def _refresh(self) -> None:
        if self._suspended or self._live is None or not self._started:
            return
        try:
            self._live.refresh()
        except Exception:  # noqa: BLE001 - cosmetic path
            pass

    # ------------------------------------------------------------------
    # State reduction (called by stream_query's event loop)
    # ------------------------------------------------------------------

    def update(
        self,
        message: str,
        *,
        color: str = "cyan",
        tail: bool = False,
        ok: bool | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Update the current stage and append a rolling activity entry.

        ``tail`` is kept for signature compatibility (the old single-line
        renderer used it to keep the end of a preview); rich now word-wraps, so
        it only affects which end of an overlong label survives ``_clean``.
        """
        label = _one_line(message, max(12, self._width - 10))
        if tail and len(message) > max(12, self._width - 10):
            label = _one_line(message[-(max(12, self._width - 10) * 2) :], self._width - 10)
        label = label or "Working"
        changed = label != self._state.phase
        self._state.phase = label
        self._state.color = color
        self._state.updated_at = time.time()
        if changed:
            self._state.append_activity(
                Activity(label=label, color=color, ok=ok, duration_ms=duration_ms, at=time.time())
            )
        elif (
            (ok is not None or duration_ms is not None)
            and self._state.activity
            and self._state.activity[-1].kind != "reasoning"
        ):
            # Tool success/timing belongs to the tool row, never to a
            # reasoning row left at the tail by a repeated phase label.
            last = self._state.activity[-1]
            if ok is not None:
                last.ok = ok
            if duration_ms is not None:
                last.duration_ms = duration_ms
        if changed:
            self._refresh()

    def set_step(self, step: int | None, steps: int | None) -> None:
        self._state.step = step
        self._state.steps = steps
        self._state.updated_at = time.time()
        self._refresh()

    def set_tool(self, tool: str | None, args_preview: str | None = None) -> None:
        self._state.current_tool = _one_line(tool, 40) or None
        self._state.tool_args_preview = _one_line(args_preview, self._width - 24) or None
        self._state.updated_at = time.time()
        self._refresh()

    def update_tool_activity(self, message: str, *, color: str = "cyan") -> None:
        """Refresh the in-flight tool row in place instead of appending.

        Partial tool-arg chunks stream as a growing label (``run_command sleep``,
        ``run_command sleep 180``, …). Each one used to append a new Activity row,
        flooding the tail with near-duplicate ``· run_command`` lines. This updates
        the current phase and the last in-flight tool row together so one row grows
        as the command assembles — mirroring how :meth:`add_reasoning` handles
        cumulative narration.
        """
        label = _one_line(message, max(12, self._width - 10)) or "Working"
        self._state.phase = label
        self._state.color = color
        self._state.updated_at = time.time()
        activity = self._state.activity
        if activity and activity[-1].kind == "event" and activity[-1].ok is None:
            activity[-1].label = label
            activity[-1].color = color
        else:
            self._state.append_activity(Activity(label=label, color=color, at=time.time()))
        self._refresh()

    def set_tokens(self, total: int | None) -> None:
        self._state.total_tokens = total
        self._state.updated_at = time.time()
        self._refresh()

    def add_failure(self) -> None:
        self._state.failed_tools += 1
        self._refresh()

    def set_answer_preview(self, text: str | None) -> None:
        self._state.answer_preview = _one_line(text, self._width - 12) or None
        self._state.updated_at = time.time()
        self._refresh()

    def clear_answer_preview(self) -> None:
        self._state.answer_preview = None
        self._refresh()

    def add_reasoning(self, text: str) -> None:
        """Mirror intermediate ``Narration`` into the activity tail.

        ACP projects the same text as ``agent_thought_chunk`` so hosts can see
        the agent's reasoning between tool calls; the CLI keeps it as a rolling
        history row so it survives the answer-preview reset on ``ToolStarted``.

        The bridge emits the *cumulative* answer for the current stretch, so one
        row is updated in place instead of appending N ever-growing prefixes. A
        new stretch starts as soon as another event appends a row (tool call or
        result), which interleaves reasoning and tool activity in order.
        """
        full = _one_line(text, _REASONING_MAX_CHARS)
        if not full:
            return
        label = _one_line(full, max(12, self._width - 12))
        activity = self._state.activity
        continuation = bool(
            self._last_reasoning
            and full.startswith(self._last_reasoning)
            and activity
            and activity[-1].kind == "reasoning"
        )
        self._state.updated_at = time.time()
        if continuation:
            activity[-1].label = label
            # ``Live``'s auto-refresh picks up the mutated state; forcing a
            # frame per streamed token would repaint the whole panel at token
            # rate, which is exactly what the old single-line spinner did.
        else:
            self._state.append_activity(
                Activity(label=label, kind="reasoning", color="cyan", at=time.time())
            )
            self._refresh()
        self._last_reasoning = full

    # ------------------------------------------------------------------
    # Interleaved output
    # ------------------------------------------------------------------

    def write_through(self, text: str, target: TextIO) -> None:
        """Write other writers' text without tearing the live region.

        When ``Live`` is active, rich's render hook repositions the cursor and
        prints this text *above* the live panel. When it is not (non-TTY, or
        after the final snapshot) the text goes straight to ``target`` so
        piped/scripted output stays byte-identical.
        """
        if self._live is None or not self._started:
            target.write(text)
            target.flush()
            return
        try:
            from rich.text import Text

            self._live.console.print(Text(text.rstrip("\n")), soft_wrap=True)
        except Exception:  # noqa: BLE001 - never lose user-visible output
            target.write(text)
            target.flush()

    def blank(self) -> None:
        """Suspend event-driven refreshes while another writer emits text."""
        self._suspended = True
        if self._live is not None and self._started:
            try:
                self._live.refresh()
            except Exception:  # noqa: BLE001 - cosmetic path
                pass

    def repaint(self) -> None:
        """Resume refreshes after a ``blank()`` and force one frame."""
        self._suspended = False
        self._refresh()

    # ------------------------------------------------------------------
    # Terminal state / snapshot
    # ------------------------------------------------------------------

    def finalize(
        self,
        status: str = "DONE",
        *,
        duration_s: float | None = None,
        tokens: int | None = None,
    ) -> None:
        """Freeze the panel as a visible snapshot (idempotent).

        ``transient=False`` means ``Live.stop()`` leaves the last frame on
        screen; no erase bytes are emitted, so a PAUSED snapshot and the
        questions printed after it are both visible.
        """
        if self._finalized:
            return
        self._finalized = True
        self._state.status = status
        if duration_s is not None:
            self._state.elapsed_override = duration_s
        if tokens is not None:
            self._state.total_tokens = tokens
        self._state.updated_at = time.time()
        live, self._live = self._live, None
        self._started = False
        if live is not None:
            try:
                live.refresh()
                live.stop()
            except Exception:  # noqa: BLE001 - cosmetic path
                pass
        self._restore_logging()

    async def stop(self, status: str = "DONE") -> None:
        """Stop the display; ``__aexit__`` derives FAILED/DONE automatically."""
        self.finalize(status)
