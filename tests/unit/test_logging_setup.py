"""Tests for fj CLI logging quieting."""

from __future__ import annotations

import logging
import os
from io import StringIO

import pytest

from flowjet.cli.agent import configure_cli_logging


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


def test_verbose_console_keeps_exception_summary_one_line() -> None:
    """With -v, logger.exception output keeps the cause on one line.

    The old behavior stripped exc_info entirely, hiding the root cause even
    in verbose mode.
    """
    from flowjet.cli.cli import _CompactConsoleFormatter

    root = logging.getLogger()
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.WARNING)
    handler.setFormatter(_CompactConsoleFormatter("%(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    try:
        try:
            raise ValueError("boom detail")
        except ValueError:
            logging.getLogger("soothe_nano.plugin").exception("tool failed")
    finally:
        root.removeHandler(handler)
        handler.close()
    out = stream.getvalue()
    assert "tool failed" in out
    assert "ValueError: boom detail" in out
    assert "Traceback" not in out
    assert out.count("\n") == 1


def _remove_file_log_handler() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "name", None) == "fj-file":
            root.removeHandler(handler)
            handler.close()


def test_file_log_handler_attached_once(tmp_path, monkeypatch) -> None:
    from flowjet.cli.cli import _FJ_FILE_HANDLER, configure_cli_logging

    monkeypatch.setenv("FJ_LOG_FILE", str(tmp_path / "fj.log"))
    configure_cli_logging()
    configure_cli_logging(verbose=True)
    try:
        names = [getattr(h, "name", None) for h in logging.getLogger().handlers]
        assert names.count(_FJ_FILE_HANDLER) == 1
        assert (tmp_path / "fj.log").exists()
    finally:
        _remove_file_log_handler()


def test_write_cli_error_mirrors_to_file_log(tmp_path, monkeypatch) -> None:
    from flowjet.cli.cli import configure_cli_logging
    from flowjet.cli.stream import write_cli_error

    log_file = tmp_path / "fj.log"
    monkeypatch.setenv("FJ_LOG_FILE", str(log_file))
    configure_cli_logging()
    try:
        try:
            raise ValueError("boom")
        except ValueError as exc:
            write_cli_error(exc, err=StringIO())
        content = log_file.read_text(encoding="utf-8")
        assert "run failed: error: ValueError: boom" in content
        # The file keeps the full traceback, unlike the compact console.
        assert "Traceback" in content
    finally:
        _remove_file_log_handler()


def test_write_cli_error_no_file_log_is_silent_on_disk(tmp_path, monkeypatch) -> None:
    from flowjet.cli.cli import configure_cli_logging
    from flowjet.cli.stream import write_cli_error

    monkeypatch.delenv("FJ_LOG_FILE", raising=False)
    configure_cli_logging()
    write_cli_error(ValueError("boom"), err=StringIO())
    assert list(tmp_path.iterdir()) == []



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


def test_silence_after_plugins_reapplies(monkeypatch: pytest.MonkeyPatch) -> None:
    from flowjet.cli.agent import silence_after_plugins

    calls: list[bool] = []
    monkeypatch.setattr(
        "flowjet.cli.agent.configure_cli_logging",
        lambda *, verbose=False: calls.append(verbose),
    )
    silence_after_plugins(verbose=True)
    assert calls == [True]


def test_compact_formatter_summarizes_exception_on_one_line() -> None:
    from flowjet.cli.agent import _CompactConsoleFormatter

    formatter = _CompactConsoleFormatter("%(message)s")
    record = logging.LogRecord(
        name="t",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed",
        args=(),
        exc_info=None,
    )
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        record.exc_info = sys.exc_info()
    rendered = formatter.format(record)
    assert rendered == "failed: RuntimeError: boom"
    assert "\n" not in rendered
    assert formatter.formatException(record.exc_info) == ""


def test_remove_root_console_preserves_file_handler(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from logging.handlers import RotatingFileHandler

    from flowjet.cli.agent import configure_cli_logging

    root = logging.getLogger()
    path = tmp_path / "app.log"
    file_handler = RotatingFileHandler(path)
    file_handler.set_name("keep-me")
    root.addHandler(file_handler)
    stream = logging.StreamHandler()
    root.addHandler(stream)
    try:
        configure_cli_logging()
        assert file_handler in root.handlers
        assert stream not in root.handlers
    finally:
        root.removeHandler(file_handler)
        file_handler.close()
        if stream in root.handlers:
            root.removeHandler(stream)
            stream.close()
