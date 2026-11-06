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


def test_write_thread_list_falls_back_when_render_module_missing(monkeypatch: Any) -> None:
    """A missing ``flowjet.cli.render`` module must not crash ``fj threads -l``.

    Regression guard for ``ModuleNotFoundError: No module named
    'flowjet.cli.render'`` observed with stale/partial installs: the caller
    falls back to plain columns instead of raising.
    """
    from flowjet.cli.threads import ThreadInfo, write_thread_list

    # Force the lazy ``from flowjet.cli.render import ...`` to fail.
    monkeypatch.setitem(sys.modules, "flowjet.cli.render", None)
    buf = io.StringIO()
    write_thread_list(
        [ThreadInfo(thread_id="tid-1", updated_at="2026-10-31 09:00", preview="hello")],
        buf,
    )
    out = buf.getvalue()
    assert "tid-1" in out and "hello" in out


def test_answer_finish_falls_back_when_render_module_missing(monkeypatch: Any) -> None:
    """A missing ``flowjet.cli.render`` module must not crash answer finishing.

    The finalized answer text is written raw instead of raising
    ``ModuleNotFoundError`` after the answer is already buffered.
    """
    from flowjet.cli.dashboard import ProgressDashboard
    from flowjet.cli.stream import AnswerWriter

    monkeypatch.setitem(sys.modules, "flowjet.cli.render", None)
    buf = io.StringIO()
    writer = AnswerWriter(stdout=buf, status=ProgressDashboard(enabled=False), live=False)
    writer.set("# Title\n\nsome **bold** text")
    writer.finish()
    out = buf.getvalue()
    assert "# Title" in out and "bold" in out


# ---------------------------------------------------------------------------
# write_questions — shared TTY renderer for stream_query and fjf resume
# ---------------------------------------------------------------------------

_LONG_DESCRIPTION = (
    "Use a long-lived service API key stored in the environment; this is the "
    "simplest option when the integration runs on a trusted backend with a "
    "secret store and needs no browser redirect at all."
)

_QUESTIONS: list[dict[str, Any]] = [
    {
        "header": "Auth method",
        "question": "Which auth method should I use for the new integration?",
        "options": [
            {"label": "API Key (Recommended)", "description": _LONG_DESCRIPTION},
            {"label": "OAuth", "description": "Use the OAuth authorization-code flow."},
            {"label": "mTLS", "description": "Use mutual TLS client certificates."},
        ],
    },
    {
        "header": "Scope",
        "question": "How wide should the first rollout be?",
        "options": [
            {"label": "Team only (Recommended)", "description": "Limit to one team."},
            {"label": "Whole org", "description": "Enable for every workspace."},
            {"label": "Canary", "description": "Start with 5% of traffic."},
        ],
    },
]


def test_write_questions_skips_non_tty_for_byte_identical_plain_fallback() -> None:
    from flowjet.cli.render import write_questions
    from flowjet.cli.stream import format_questions_block

    buf = io.StringIO()
    assert write_questions(_QUESTIONS, "t-123", buf) is False
    assert buf.getvalue() == ""
    # The caller writes the historical plain-text block unchanged.
    plain = format_questions_block(tuple(_QUESTIONS), "t-123")
    buf.write(plain)
    assert buf.getvalue() == plain


def test_write_questions_renders_partitioned_tty_panel() -> None:
    from flowjet.cli.render import write_questions

    buf = TTYBuffer()
    assert write_questions(_QUESTIONS, "t-123", buf, width=60, color=False)
    out = buf.getvalue()
    assert "Q1" in out and "Q2" in out
    assert "[Auth method]" in out and "[Scope]" in out
    assert "Which auth method" in out and "How wide" in out
    assert "1." in out and "2." in out and "3." in out
    assert "API Key (Recommended)" in out
    assert "★" in out  # recommended marker
    assert "Resume with: fjf -t t-123 <your answer>" in out
    assert "\x1b" not in out

    lines = out.splitlines()
    assert len(lines) > 14  # partitioned, multi-line region (not one line)
    assert all(len(line) <= 60 for line in lines)
    # Long descriptions word-wrap with aligned indentation rather than being cut.
    # Phrases may straddle a wrap boundary, so check individual tokens.
    for fragment in ("long-lived", "trusted", "secret", "store", "browser", "redirect"):
        assert fragment in out
    continuation = [
        line
        for line in lines
        if "environment; this" in line or "store and needs" in line or "browser redirect" in line
    ]
    assert len(continuation) >= 2
    assert all(line.startswith("│      ") for line in continuation)


def test_write_questions_resume_hint_controls_cli_footer() -> None:
    from flowjet.cli.render import write_questions

    no_footer = TTYBuffer()
    assert write_questions(_QUESTIONS, "t-123", no_footer, resume_hint="", width=60, color=False)
    assert "Resume with:" not in no_footer.getvalue()
    assert "fjf -t" not in no_footer.getvalue()

    custom = TTYBuffer()
    assert write_questions(
        _QUESTIONS,
        "t-123",
        custom,
        resume_hint="Answer in the host input.",
        width=60,
        color=False,
    )
    assert "Answer in the host input." in custom.getvalue()
    assert "Resume with:" not in custom.getvalue()


def test_write_questions_strips_untrusted_control_characters() -> None:
    from flowjet.cli.render import write_questions

    questions = [
        {
            "header": "Injected\x1b[31m",
            "question": "Pick\r\none \x00option",
            "options": [
                {"label": "Bad\x1b[2J (Recommended)", "description": "line1\nline2\x07"},
            ],
        }
    ]
    buf = TTYBuffer()
    assert write_questions(questions, "t-\r1", buf, width=60, color=False)
    out = buf.getvalue()
    assert "\x1b" not in out and "\x00" not in out and "\x07" not in out
    assert "Injected" in out and "Pick one option" in out
    assert "★" in out


def test_write_questions_empty_questions_still_renders_pause_panel() -> None:
    from flowjet.cli.render import write_questions

    buf = TTYBuffer()
    assert write_questions([], "t-123", buf, width=60, color=False)
    assert "Paused for input" in buf.getvalue()
    assert "Resume with: fjf -t t-123 <your answer>" in buf.getvalue()


def test_write_questions_falls_back_when_rich_missing(monkeypatch: Any) -> None:
    from flowjet.cli.render import write_questions

    monkeypatch.setitem(sys.modules, "rich.panel", None)
    buf = TTYBuffer()
    assert not write_questions(_QUESTIONS, "t-123", buf)
    assert buf.getvalue() == ""
