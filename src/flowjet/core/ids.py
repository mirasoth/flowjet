"""Centralized random id generators for FlowJet runtime surfaces.

All server/CLI allocated ids flow through here so the format, entropy, and
prefix are defined in exactly one place. Every id is a short, opaque,
filesystem-safe token built from 16 hex chars (``uuid4().hex[:16]``, ~64 bits
of entropy) — enough to avoid collisions for a single-user/local coding agent
while staying readable in logs and UIs.

The full ``uuid4()`` string (36 chars with dashes) and the untruncated
``uuid4().hex`` (32 chars) carried no extra entropy and were needlessly long
in logs/UI, so they are no longer used anywhere in the project.

Session/thread ids carry no prefix: they are the bare 16-hex token itself
(e.g. ``550e8400e29b7800``), which is what ``fjf`` reads from the active-thread
pointer to continue a session.
"""

from __future__ import annotations

from uuid import uuid4

#: Number of hex chars taken from ``uuid4().hex`` for all FlowJet ids.
#:
#: 16 hex chars = 64 bits of entropy. A 50% collision probability is reached
#: at ~1.8e19 ids (birthday bound), which is far beyond any single FlowJet
#: deployment's lifetime.
_HEX_LEN = 16

#: Prefix for FlowJet-allocated run/response ids.
_RUN_PREFIX = "resp_"

#: Prefix for ACP session/run ids.
_ACP_PREFIX = "acp-"

#: Prefix for OpenAI-compatible Responses API message item ids.
_MESSAGE_PREFIX = "msg_"

#: Prefix for OpenAI-compatible Chat Completions response ids.
_CHATCMPL_PREFIX = "chatcmpl_"


def short_hex() -> str:
    """Return a bare 16-hex-char token, e.g. ``550e8400e29b7800``.

    Use this for internal correlation tokens that carry their own prefix or
    no prefix at all (e.g. clarification interrupt ids embedded in a URI).
    """
    return uuid4().hex[:_HEX_LEN]


def new_session_id() -> str:
    """Allocate a fresh session/thread id, e.g. ``550e8400e29b7800``.

    The id is the bare 16-hex token with no prefix — the same value the CLI
    shows in the ``Done · <duration> · <thread_id>`` footer and ``fjf`` reads
    from the active-thread pointer to continue a session.
    """
    return short_hex()


def new_run_id() -> str:
    """Allocate a fresh run/response id, e.g. ``resp_550e8400e29b7800``."""
    return f"{_RUN_PREFIX}{short_hex()}"


def new_acp_id() -> str:
    """Allocate a fresh ACP session/run id, e.g. ``acp-550e8400e29b7800``."""
    return f"{_ACP_PREFIX}{short_hex()}"


def new_message_id() -> str:
    """Allocate a fresh Responses API message item id, e.g. ``msg_550e8400e29b7800``."""
    return f"{_MESSAGE_PREFIX}{short_hex()}"


def new_chatcmpl_id() -> str:
    """Allocate a fresh Chat Completions response id, e.g. ``chatcmpl_550e8400e29b7800``."""
    return f"{_CHATCMPL_PREFIX}{short_hex()}"
