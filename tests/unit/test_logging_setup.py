"""Tests for fj CLI logging quieting."""

from __future__ import annotations

import logging
import os
from io import StringIO

import pytest

from fj_ai.logging_setup import configure_cli_logging


def test_configure_cli_logging_opts_out_of_browser_use_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BROWSER_USE_SETUP_LOGGING", raising=False)
    configure_cli_logging()
    assert os.environ["BROWSER_USE_SETUP_LOGGING"] == "false"


def test_configure_cli_logging_preserves_explicit_browser_use_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BROWSER_USE_SETUP_LOGGING", "true")
    configure_cli_logging()
    assert os.environ["BROWSER_USE_SETUP_LOGGING"] == "true"


def test_configure_cli_logging_removes_root_console_handler() -> None:
    root = logging.getLogger()
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)-8s [%(name)s] %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        configure_cli_logging()
        assert handler not in root.handlers
        logging.getLogger("soothe_nano.agent.builder").info("should not reach console")
        assert stream.getvalue() == ""
    finally:
        if handler in root.handlers:
            root.removeHandler(handler)
        handler.close()


def test_configure_cli_logging_suppresses_exception_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_cli_logging(verbose=False)
    try:
        raise TypeError("WizsearchSearchTool._arun() got an unexpected keyword argument 'limit'")
    except TypeError:
        logging.getLogger("soothe_nano.utils.tool_error_handler").exception(
            "wizsearch_search failed: TypeError: boom"
        )
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "unexpected keyword argument" not in captured.err


def test_configure_cli_logging_verbose_one_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_cli_logging(verbose=True)
    try:
        raise TypeError("unexpected keyword argument 'limit'")
    except TypeError:
        logging.getLogger("soothe_nano.utils.tool_error_handler").exception(
            "wizsearch_search failed: TypeError: unexpected keyword argument 'limit'"
        )
    captured = capsys.readouterr()
    assert "wizsearch_search failed" in captured.err
    assert "Traceback" not in captured.err
