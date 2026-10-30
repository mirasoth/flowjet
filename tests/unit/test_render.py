"""Unit tests for the lazy rich rendering helpers (flowjet.cli.render)."""

from __future__ import annotations

import io
import re
import sys
from typing import Any

from flowjet.cli.threads import ThreadInfo


class TTYBuffer(io.StringIO):
    """StringIO that claims to be a terminal (drives the rich code path)."""

    def isatty(self) -> bool:
        return True


_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def test_answer_markdown_skips_non_tty() -> None:
    from flowjet.cli.render import write_answer_markdown

    buf = io.StringIO()
    # Non-TTY: nothing written by the helper; caller falls back to raw text.
    assert not write_answer_markdown("# Title\n\nbody", buf)
    assert buf.getvalue() == ""


def test_answer_markdown_renders_on_tty() -> None:
    from flowjet.cli.render import write_answer_markdown

    buf = TTYBuffer()
    assert write_answer_markdown("# Title\n\nsome **bold** text", buf)
    out = buf.getvalue()
    assert "Title" in out and "bold" in out
    # Rendered output carries ANSI styling (this is the rich path).
    assert _ANSI_RE.search(out)


def test_answer_markdown_empty_text_is_noop() -> None:
    from flowjet.cli.render import write_answer_markdown

    buf = TTYBuffer()
    assert not write_answer_markdown("", buf)
    assert buf.getvalue() == ""


def test_answer_markdown_literal_brackets_survive() -> None:
    from flowjet.cli.render import write_answer_markdown

    buf = TTYBuffer()
    text = "see [TODO-123] for details"
    assert write_answer_markdown(text, buf)
    # markup=False: ``[...]`` is data, not a rich style tag.
    assert "[TODO-123]" in buf.getvalue()


def test_thread_table_renders_on_tty() -> None:
    from flowjet.cli.render import write_thread_table

    threads = [
        ThreadInfo(thread_id="tid-1", updated_at="2026-10-30 10:00:00", preview="hello world"),
        ThreadInfo(thread_id="tid-2", updated_at=None, preview=None),
    ]
    buf = TTYBuffer()
    assert write_thread_table(threads, buf)
    out = buf.getvalue()
    assert "tid-1" in out and "hello world" in out
    assert "tid-2" in out
    assert "Updated" in out
    assert _ANSI_RE.search(out)


def test_thread_table_skips_non_tty_and_empty() -> None:
    from flowjet.cli.render import write_thread_table

    threads = [ThreadInfo(thread_id="tid-1")]
    plain = io.StringIO()
    assert not write_thread_table(threads, plain)
    assert plain.getvalue() == ""
    assert not write_thread_table([], TTYBuffer())


def test_thread_table_falls_back_when_rich_missing(monkeypatch: Any) -> None:
    from flowjet.cli.render import write_thread_table

    # Any rich import failing must degrade to False (caller uses plain text).
    monkeypatch.setitem(sys.modules, "rich.table", None)
    buf = TTYBuffer()
    assert not write_thread_table([ThreadInfo(thread_id="tid-1")], buf)
    assert buf.getvalue() == ""
