"""Tests for CLI error formatting."""

from __future__ import annotations

from io import StringIO

from flowjet.cli.stream import (
    format_cli_error,
    write_cli_error,
)
from flowjet.core.streaming.tool_results import ToolResultInspector


def test_tool_result_error_detail_from_string() -> None:
    detail = ToolResultInspector.error_detail(
        "Error: TypeError: WizsearchSearchTool._arun() got an unexpected keyword argument 'limit'"
    )
    assert detail is not None
    assert "unexpected keyword argument" in detail


def test_tool_result_error_detail_from_dict() -> None:
    assert ToolResultInspector.error_detail({"error": "boom"}) == "boom"
    assert ToolResultInspector.error_detail({"error": ""}) is None
    assert ToolResultInspector.error_detail({"ok": True}) is None
    assert ToolResultInspector.error_detail("ok results") is None


def test_tool_result_error_detail_non_string() -> None:
    assert ToolResultInspector.error_detail(None) is None
    assert ToolResultInspector.error_detail(42) is None
    assert ToolResultInspector.error_detail(["error"]) is None


def test_tool_result_error_detail_empty_and_prefixes() -> None:
    assert ToolResultInspector.error_detail("   ") is None
    assert ToolResultInspector.error_detail("error: not found") == "not found"
    assert ToolResultInspector.error_detail("ERROR: boom") == "boom"
    # Trailing space is stripped before prefix match, so bare "Error:" is not an error payload.
    assert ToolResultInspector.error_detail("Error:") is None


def test_tool_result_error_detail_json_string() -> None:
    assert ToolResultInspector.error_detail('{"error": "disk full"}') == "disk full"
    assert ToolResultInspector.error_detail('{"error": ""}') is None
    assert ToolResultInspector.error_detail('{"ok": true}') is None
    assert ToolResultInspector.error_detail('{"error": "broken"') is None  # invalid JSON


def test_simplify_unexpected_keyword() -> None:
    raw = "TypeError: WizsearchSearchTool._arun() got an unexpected keyword argument 'limit'"
    assert ToolResultInspector.simplify_error(raw) == "unexpected argument 'limit'"


def test_simplify_missing_argument() -> None:
    raw = "missing 1 required positional argument: 'query'"
    assert ToolResultInspector.simplify_error(raw) == "missing argument 'query'"
    raw2 = "TypeError: missing 2 required positional arguments: 'a' and 'b'"
    assert ToolResultInspector.simplify_error(raw2) == "missing argument 'a' and 'b'"


def test_simplify_strips_exception_prefix_and_method() -> None:
    assert ToolResultInspector.simplify_error("ValueError: bad path") == "bad path"
    assert ToolResultInspector.simplify_error("Foo.bar() exploded") == "exploded"
    assert ToolResultInspector.simplify_error("   ") == ""


def test_format_cli_error_one_line() -> None:
    exc = RuntimeError("provider unreachable\nmore detail")
    assert format_cli_error(exc) == "error: RuntimeError: provider unreachable"


def test_format_cli_error_empty_and_prefixed() -> None:
    assert format_cli_error(RuntimeError("")) == "error: RuntimeError"
    assert format_cli_error(ValueError("ValueError: already prefixed")) == (
        "error: ValueError: already prefixed"
    )
    assert format_cli_error(RuntimeError("RuntimeError something")) == (
        "error: RuntimeError something"
    )


def test_format_cli_error_strips_type_chain() -> None:
    """Triple-nested type prefixes should be stripped to the human message."""
    raw = (
        "InternalServerError: litellm.InternalServerError: InternalServerError: "
        "OpenAIException - Missing credentials. Please pass an `api_key`, "
        "`workload_identity`, `admin_api_key`, or set the `OPENAI_API_KEY` "
        "or `OPENAI_ADMIN_KEY` environment variable."
    )
    exc = RuntimeError(raw)
    exc_type = "InternalServerError"
    exc.exc_type = exc_type  # type: ignore[attr-defined]
    result = format_cli_error(exc)
    # Known-error pattern → friendly summary, no type-chain noise.
    assert result == "error: Missing API key"


def test_format_cli_error_strips_type_chain_unknown() -> None:
    """For unknown errors, type-chain prefixes are stripped but message kept."""
    raw = "ValueError: ValueError: something broke"
    exc = ValueError(raw)
    result = format_cli_error(exc)
    assert result == "error: ValueError: something broke"


def test_format_cli_error_missing_credentials_hint() -> None:
    """Missing-credentials errors produce a friendly summary + hint."""
    from flowjet.cli.stream import _error_hint

    raw = (
        "InternalServerError: litellm.InternalServerError: InternalServerError: "
        "OpenAIException - Missing credentials. Please pass an `api_key`."
    )
    exc = RuntimeError(raw)
    exc.exc_type = "InternalServerError"  # type: ignore[attr-defined]
    assert format_cli_error(exc) == "error: Missing API key"
    hint = _error_hint(exc)
    assert hint is not None
    assert "OPENAI_API_KEY" in hint


def test_write_cli_error_prints_hint_for_known_error() -> None:
    """Known errors should print an actionable hint line."""
    err = StringIO()
    raw = (
        "InternalServerError: litellm.InternalServerError: InternalServerError: "
        "OpenAIException - Missing credentials. Please pass an `api_key`."
    )
    exc = RuntimeError(raw)
    exc.exc_type = "InternalServerError"  # type: ignore[attr-defined]
    write_cli_error(exc, verbose=False, err=err)
    output = err.getvalue()
    assert "error: Missing API key" in output
    assert "→" in output
    assert "OPENAI_API_KEY" in output


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
