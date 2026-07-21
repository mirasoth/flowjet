"""LLM intent provider via soothe-nano ``create_chat_model("fast")``."""

from __future__ import annotations

import logging
import re
from typing import Any

from fj_ai.completion.context import CompletionContext

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an autocomplete engine for the fj coding-agent CLI.
Predict the user's intended natural-language query.

Rules:
- Return exactly 5 candidates, one per line.
- Each candidate is a full query continuation (not a shell command).
- Do not explain.
- Do not execute.
- Do not include markdown, bullets, or numbering.
- Do not prefix with "fj".
- Prefer repository-aware suggestions.
- Each line must be independently usable after: fj <candidate>
"""

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_FJ_PREFIX_RE = re.compile(r"^\s*fj\s+", re.IGNORECASE)


def build_user_prompt(ctx: CompletionContext) -> str:
    """Compact user prompt from slim context."""
    lines = [
        f"cwd: {ctx.cwd}",
    ]
    if ctx.project_root:
        lines.append(f"project_root: {ctx.project_root.name} ({ctx.project_root})")
    if ctx.language:
        lines.append(f"language: {ctx.language}")
    if ctx.project_type:
        lines.append(f"project_type: {ctx.project_type}")
    if ctx.git_repo:
        lines.append(f"git_branch: {ctx.git_branch or '?'}")
        if ctx.staged_names:
            lines.append("staged: " + ", ".join(ctx.staged_names))
        if ctx.modified_names:
            lines.append("modified: " + ", ".join(ctx.modified_names))
    if ctx.recent_history:
        lines.append("recent_history:")
        for item in ctx.recent_history[:8]:
            lines.append(f"- {item}")
    lines.append(f"current_input: {ctx.query_prefix or '(empty)'}")
    if not ctx.query_prefix:
        lines.append("mode: suggest useful next tasks for this workspace")
    else:
        lines.append("mode: complete or refine the current_input prefix")
    return "\n".join(lines)


def parse_candidates(text: str, *, limit: int = 5) -> list[str]:
    """Parse model output into clean candidate strings."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = _BULLET_RE.sub("", line).strip()
        line = _FJ_PREFIX_RE.sub("", line).strip()
        line = line.strip("`\"'")
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= limit:
            break
    return out


async def llm_candidates(
    ctx: CompletionContext,
    config: Any,
    *,
    limit: int = 5,
) -> list[str]:
    """Call the configured fast-role chat model; never boots an agent."""
    try:
        model = config.create_chat_model("fast")
    except Exception:
        logger.debug("create_chat_model(fast) failed", exc_info=True)
        return []

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(ctx)},
    ]
    try:
        result = await model.ainvoke(messages)
    except Exception:
        logger.debug("fast model ainvoke failed", exc_info=True)
        return []

    content = getattr(result, "content", result)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        content = "".join(parts)
    return parse_candidates(str(content), limit=limit)
