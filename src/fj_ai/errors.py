"""User-facing error formatting for the fj CLI."""

from __future__ import annotations

import re
import sys
import traceback
from typing import Any, TextIO


def tool_result_error_detail(content: Any) -> str | None:
    """Extract an error string from a tool result payload, if any."""
    if isinstance(content, dict):
        err = content.get("error")
        return str(err).strip() if err else None

    if not isinstance(content, str):
        return None

    text = content.strip()
    if not text:
        return None

    for prefix in ("Error: ", "error: ", "ERROR: "):
        if text.startswith(prefix):
            return text[len(prefix) :].strip() or text

    if text.startswith("{") and '"error"' in text[:80]:
        try:
            import json

            payload = json.loads(text)
        except (TypeError, ValueError):
            return None
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"]).strip()
    return None


def simplify_tool_error(detail: str) -> str:
    """Shorten common tool failure strings for the progress line."""
    text = detail.strip()
    match = re.search(r"unexpected keyword argument ['\"](\w+)['\"]", text)
    if match:
        return f"unexpected argument '{match.group(1)}'"
    match = re.search(r"missing \d+ required positional argument[s]?: (.+)$", text)
    if match:
        return f"missing argument {match.group(1)}"
    # Drop redundant exception type prefix when the message already explains itself.
    text = re.sub(r"^(TypeError|ValueError|RuntimeError|KeyError):\s*", "", text)
    text = re.sub(r"^\w+\.\w+\(\)\s+", "", text)  # e.g. Class.method()
    return text.strip() or detail.strip()


def format_cli_error(exc: BaseException) -> str:
    """One-line summary for an uncaught run failure."""
    name = type(exc).__name__
    msg = str(exc).strip()
    if not msg:
        return f"error: {name}"
    first = next((line.strip() for line in msg.splitlines() if line.strip()), msg)
    if first.startswith(name + ":"):
        return f"error: {first}"
    # Avoid "error: RuntimeError: RuntimeError: ..." duplication.
    if first.startswith(name):
        return f"error: {first}"
    return f"error: {name}: {first}"


def write_cli_error(
    exc: BaseException,
    *,
    verbose: bool = False,
    err: TextIO | None = None,
) -> None:
    """Write a clean error to stderr; include traceback only when verbose."""
    stream = err or sys.stderr
    stream.write(format_cli_error(exc) + "\n")
    if verbose:
        stream.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    stream.flush()
