"""Tests for CLI error formatting."""

from __future__ import annotations

from io import StringIO

from fj_ai.errors import (
    format_cli_error,
    simplify_tool_error,
    tool_result_error_detail,
    write_cli_error,
)


def test_tool_result_error_detail_from_string() -> None:
    detail = tool_result_error_detail(
        "Error: TypeError: WizsearchSearchTool._arun() got an unexpected keyword argument 'limit'"
    )
    assert detail is not None
    assert "unexpected keyword argument" in detail


def test_tool_result_error_detail_from_dict() -> None:
    assert tool_result_error_detail({"error": "boom"}) == "boom"
    assert tool_result_error_detail("ok results") is None


def test_simplify_unexpected_keyword() -> None:
    raw = "TypeError: WizsearchSearchTool._arun() got an unexpected keyword argument 'limit'"
    assert simplify_tool_error(raw) == "unexpected argument 'limit'"


def test_format_cli_error_one_line() -> None:
    exc = RuntimeError("provider unreachable\nmore detail")
    assert format_cli_error(exc) == "error: RuntimeError: provider unreachable"


def test_write_cli_error_verbose_includes_traceback() -> None:
    err = StringIO()

    def boom() -> None:
        raise ValueError("bad")

    try:
        boom()
    except ValueError as exc:
        write_cli_error(exc, verbose=False, err=err)
        quiet = err.getvalue()
        err.seek(0)
        err.truncate()
        write_cli_error(exc, verbose=True, err=err)
        noisy = err.getvalue()

    assert quiet == "error: ValueError: bad\n"
    assert "Traceback" in noisy
    assert "ValueError: bad" in noisy
