"""Centralized random id generators for FlowJet runtime surfaces.

All server/CLI allocated ids flow through here so the format, entropy, and
prefix are defined in exactly one place. The session id is a short, opaque,
filesystem-safe token (``fj-`` + 16 hex chars, ~64 bits of entropy) — enough
to avoid collisions for a single-user/local coding agent while staying
readable in logs and UIs.
"""

from __future__ import annotations

from uuid import uuid4

#: Prefix for FlowJet-allocated session ids.
_SESSION_PREFIX = "fj-"

#: Prefix for FlowJet-allocated run/response ids.
_RUN_PREFIX = "resp_"

#: Number of hex chars taken from ``uuid4().hex`` for session ids.
#:
#: 16 hex chars = 64 bits of entropy. A 50% collision probability is reached
#: at ~1.8e19 sessions (birthday bound), which is far beyond any single
#: FlowJet deployment's lifetime. The full ``uuid4()`` string (36 chars with
#: dashes) carried no extra entropy and was needlessly long in logs/UI.
_SESSION_HEX_LEN = 16

#: Number of hex chars taken from ``uuid4().hex`` for run/response ids.
_RUN_HEX_LEN = 16


def new_session_id() -> str:
    """Allocate a fresh session/thread id, e.g. ``fj-550e8400e29b7800``."""
    return f"{_SESSION_PREFIX}{uuid4().hex[:_SESSION_HEX_LEN]}"


def new_run_id() -> str:
    """Allocate a fresh run/response id, e.g. ``resp_550e8400e29b7800``."""
    return f"{_RUN_PREFIX}{uuid4().hex[:_RUN_HEX_LEN]}"
