"""Rich terminal rendering for the fj CLI (lazy, TTY-only, plain-text fallback).

``rich`` is imported lazily so ``fj -V`` / ``fj -h`` / completion paths never
pay the import cost. Every helper is a no-op (returns ``False``) when the
target stream is not a TTY or rich is unavailable — piped/scripted output
stays byte-identical to the plain-text form, and the callers fall back to it.

The dashboard (``flowjet.cli.dashboard``) and the ``ask_user`` question block
share :func:`make_console` / :func:`render_to_text` / :func:`terminal_metrics`
so width, colour and markup conventions live in one place.
"""

from __future__ import annotations

import io
import re
import shutil
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from flowjet.cli.threads import ThreadInfo

# Event payloads (tool args, model narration, question labels/descriptions) are
# untrusted. Strip terminal control characters before they reach a renderer so
# a payload cannot inject escape sequences or smash the live region.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_ANSI_RE = re.compile(r"\033\[[0-9;?]*[ -/]*[@-~]")
# Generous ceilings: rich word-wraps long prose, these only stop pathological
# payloads from flooding the terminal.
_MAX_QUESTION_CHARS = 1000
_MAX_LABEL_CHARS = 200
_MAX_DESCRIPTION_CHARS = 2000


def _is_tty(out: TextIO) -> bool:
    """Best-effort TTY check (some TextIO impls lack ``isatty``)."""
    isatty = getattr(out, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except Exception:  # noqa: BLE001 - any probe failure means "not a terminal"
        return False


def _clean(value: Any, *, limit: int) -> str:
    """Single-line, control-character-free, length-bounded text for a panel."""
    if value is None:
        return ""
    text = _CONTROL_RE.sub(" ", str(value))
    text = " ".join(text.split()).strip()
    if len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return text


def terminal_metrics(out: TextIO) -> tuple[int, int, bool]:
    """Return ``(width, height, colour)`` for TTY renderers.

    Width and colour come from the CLI's long-standing conventions in
    ``progress.py`` (``FJ_PROGRESS_WIDTH`` / ``NO_COLOR`` / ``FJ_FORCE_COLOR``);
    height is used to shrink the dashboard's activity tail on short terminals.
    Imported lazily to keep ``fj -V`` / completion paths free of even the
    progress module.
    """
    from flowjet.cli.progress import _color_enabled, _line_budget

    try:
        rows = shutil.get_terminal_size(fallback=(80, 24)).lines
    except OSError:
        rows = 24
    return _line_budget(), max(8, rows), _color_enabled(out)


def make_console(
    out: TextIO,
    *,
    width: int | None = None,
    color: bool | None = None,
    force_terminal: bool | None = None,
) -> Any:  # noqa: ANN401 - rich Console
    """Build a rich Console with the CLI's data-safe rendering conventions.

    ``markup``/``highlight``/``emoji`` are off because stream content is data,
    not rich markup (thread previews, answers and question labels may contain
    ``[...]`` that would otherwise be swallowed as style tags).
    """
    from rich.console import Console

    kwargs: dict[str, Any] = {
        "file": out,
        "markup": False,
        "highlight": False,
        "emoji": False,
    }
    if width is not None:
        kwargs["width"] = width
    if force_terminal is not None:
        kwargs["force_terminal"] = force_terminal
    if color is False:
        kwargs["no_color"] = True
        kwargs["color_system"] = None
    return Console(**kwargs)


def render_to_text(renderable: Any, *, width: int, color: bool) -> str:  # noqa: ANN401
    """Render a rich renderable into a string before touching the real stream.

    Rendering into an intermediate buffer means a partial/failing rich install
    can never leave half a frame on stdout, and callers can write the whole
    frame in one go (fewer flickers).
    """
    buf = io.StringIO()
    console = make_console(buf, width=width, color=color, force_terminal=True)
    console.print(renderable)
    text = buf.getvalue()
    # Styles such as bold/dim can still emit SGR codes with ``color=False``:
    # honour NO_COLOR by stripping every escape sequence from the frame.
    return text if color else _ANSI_RE.sub("", text)


def write_answer_markdown(text: str, out: TextIO) -> bool:
    """Render a markdown answer to a TTY with rich. ``False`` = caller renders plain."""
    if not text or not _is_tty(out):
        return False
    try:
        from rich.markdown import Markdown

        make_console(out).print(Markdown(text))
    except Exception:  # noqa: BLE001 - rendering must never break a finished run
        return False
    return True


def write_thread_table(threads: list[ThreadInfo], out: TextIO) -> bool:
    """Render ``fj threads -l`` as a rich table on a TTY. ``False`` = plain fallback."""
    if not threads or not _is_tty(out):
        return False
    try:
        from rich import box
        from rich.console import Group
        from rich.table import Table
        from rich.text import Text

        table = Table(
            box=box.SIMPLE,
            header_style="bold dim",
            pad_edge=False,
            show_edge=False,
        )
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Updated", style="dim", no_wrap=True)
        table.add_column("Preview")
        for t in threads:
            table.add_row(
                t.thread_id,
                t.updated_at or "",
                Text(t.preview or ""),
            )
        make_console(out).print(Group(table))
    except Exception:  # noqa: BLE001 - rendering must never break listing
        return False
    return True


def _questions_renderable(
    questions: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    thread_id: str,
    *,
    resume_hint: str | None,
) -> Any:  # noqa: ANN401 - rich Renderable
    """Build the partitioned question panel (pure rich renderable)."""
    from rich.console import Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    footer = (
        f"Resume with: fjf -t {_clean(thread_id, limit=64)} <your answer>"
        if resume_hint is None
        else _clean(resume_hint, limit=200)
    )

    blocks: list[Any] = []
    for qi, q in enumerate(questions, 1):
        header = _clean(q.get("header"), limit=_MAX_LABEL_CHARS)
        question = _clean(q.get("question"), limit=_MAX_QUESTION_CHARS)
        prefix = f"Q{qi}" if len(questions) > 1 else ""
        heading = "  ".join(part for part in (prefix, f"[{header}]" if header else "") if part)
        if heading:
            blocks.append(Text(heading, style="bold yellow"))
        if question:
            blocks.append(Text(question))

        raw_options = q.get("options")
        options = raw_options if isinstance(raw_options, (list, tuple)) else ()
        table = Table(
            box=None,
            show_header=False,
            pad_edge=False,
            padding=(0, 1),
            expand=True,
        )
        table.add_column("no", width=3, justify="right", no_wrap=True)
        table.add_column("option", ratio=1)
        for oi, opt in enumerate(options, 1):
            if not isinstance(opt, dict):
                continue
            label = _clean(opt.get("label"), limit=_MAX_LABEL_CHARS)
            desc = _clean(opt.get("description"), limit=_MAX_DESCRIPTION_CHARS)
            recommended = "Recommended" in label
            marker = " ★" if recommended else ""
            cells: list[Any] = [
                Text(f"{label}{marker}", style="bold green" if recommended else "bold")
            ]
            if desc:
                cells.append(Text(desc, style="dim"))
            table.add_row(Text(f"{oi}.", style="cyan"), Group(*cells))
        if table.row_count:
            blocks.append(table)
        if qi < len(questions):
            blocks.append(Text(""))

    if footer:
        if blocks:
            blocks.append(Text(""))
        blocks.append(Text(footer, style="bold cyan"))

    return Panel(
        Group(*blocks) if blocks else Text("Paused for input"),
        title="⏸ Paused for input",
        title_align="left",
        border_style="yellow",
        padding=(0, 1),
    )


def write_questions(
    questions: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    thread_id: str,
    out: TextIO,
    *,
    resume_hint: str | None = None,
    width: int | None = None,
    color: bool | None = None,
) -> bool:
    """Render ``ask_user`` questions as a partitioned rich panel on a TTY.

    Returns ``False`` when ``out`` is not a TTY or rich is unavailable; the
    caller must then write ``format_questions_block(...)`` unchanged so piped
    output stays byte-identical. This helper has no dependency on the live
    dashboard, so both the in-run pause (``stream.py``) and the ``fjf`` resume
    path (``cli.py``, before any dashboard exists) share one implementation.
    """
    if not _is_tty(out):
        return False
    try:
        cols, _, use_color = terminal_metrics(out)
        rendered = render_to_text(
            _questions_renderable(questions, thread_id, resume_hint=resume_hint),
            width=width or cols,
            color=use_color if color is None else color,
        )
    except Exception:  # noqa: BLE001 - fall back to the plain-text block
        return False
    out.write(rendered)
    out.flush()
    return True
