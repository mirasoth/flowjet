"""Rich terminal rendering for the fj CLI (lazy, TTY-only, plain-text fallback).

``rich`` is imported lazily so ``fj -V`` / ``fj -h`` / completion paths never
pay the import cost. Every helper is a no-op (returns ``False``) when the
target stream is not a TTY or rich is unavailable — piped/scripted output
stays byte-identical to the plain-text form, and the callers fall back to it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from flowjet.cli.threads import ThreadInfo


def _is_tty(out: TextIO) -> bool:
    """Best-effort TTY check (some TextIO impls lack ``isatty``)."""
    isatty = getattr(out, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except Exception:  # noqa: BLE001 - any probe failure means "not a terminal"
        return False


def _make_console(out: TextIO) -> Any:  # noqa: ANN401 - rich Console
    from rich.console import Console

    # markup/highlight/emoji off: stream content is data, not rich markup
    # (thread previews and answers may contain ``[...]`` that would otherwise
    # be swallowed as style tags). Markdown/Table renderables style themselves.
    return Console(file=out, markup=False, highlight=False, emoji=False)


def write_answer_markdown(text: str, out: TextIO) -> bool:
    """Render a markdown answer to a TTY with rich. ``False`` = caller renders plain."""
    if not text or not _is_tty(out):
        return False
    try:
        from rich.markdown import Markdown

        console = _make_console(out)
        console.print(Markdown(text))
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
        _make_console(out).print(Group(table))
    except Exception:  # noqa: BLE001 - rendering must never break listing
        return False
    return True
