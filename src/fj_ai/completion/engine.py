"""Completion engine: local providers + timed fast-model LLM."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from fj_ai.completion.context import DEFAULT_TASKS, CompletionContext, build_context
from fj_ai.completion.llm import llm_candidates
from fj_ai.completion.static import static_candidates

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 8
DEFAULT_LLM_TIMEOUT_S = 0.25


@dataclass(frozen=True)
class Candidate:
    text: str
    provider: str
    score: float = 0.0


def history_candidates(ctx: CompletionContext, *, limit: int = 8) -> list[Candidate]:
    """Filter recent history by query prefix."""
    prefix = ctx.query_prefix.casefold()
    out: list[Candidate] = []
    for i, item in enumerate(ctx.recent_history):
        folded = item.casefold()
        if prefix:
            if folded.startswith(prefix):
                pass
            elif len(prefix) >= 3 and prefix in folded:
                pass
            else:
                continue
        score = 0.95 - i * 0.01
        if prefix and folded.startswith(prefix):
            score += 0.05
        out.append(Candidate(text=item, provider="history", score=score))
        if len(out) >= limit:
            break
    return out


def merge_candidates(
    groups: list[list[Candidate]],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[str]:
    """Dedupe case-insensitively; preserve group priority order then score."""
    ranked: list[Candidate] = []
    for group in groups:
        ranked.extend(group)
    ranked.sort(key=lambda c: c.score, reverse=True)

    seen: set[str] = set()
    out: list[str] = []
    for cand in ranked:
        key = cand.text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cand.text)
        if len(out) >= top_k:
            break
    return out


async def complete_async(
    words: list[str],
    *,
    config: Any | None = None,
    cwd: Any | None = None,
    top_k: int = DEFAULT_TOP_K,
    llm_timeout_s: float = DEFAULT_LLM_TIMEOUT_S,
    use_llm: bool = True,
) -> list[str]:
    """Return top-k completion strings for shell display."""
    from pathlib import Path

    ctx = build_context(words, cwd=Path(cwd) if cwd else None)

    if ctx.mode == "static":
        token = ctx.query_prefix
        if ctx.words and ctx.words[-1].startswith("-"):
            token = ctx.words[-1]
        static = [Candidate(text=s, provider="static", score=0.7) for s in static_candidates(token)]
        return merge_candidates([static], top_k=top_k)

    hist = history_candidates(ctx)
    builtins = [
        Candidate(text=t, provider="builtin", score=0.4)
        for t in DEFAULT_TASKS
        if not ctx.query_prefix or t.casefold().startswith(ctx.query_prefix.casefold())
    ]

    llm: list[Candidate] = []
    if use_llm and config is not None:
        try:
            texts = await asyncio.wait_for(
                llm_candidates(ctx, config, limit=5),
                timeout=llm_timeout_s,
            )
            llm = [
                Candidate(text=t, provider="llm", score=0.82 - i * 0.01)
                for i, t in enumerate(texts)
            ]
        except TimeoutError:
            logger.debug("LLM completion timed out after %.0fms", llm_timeout_s * 1000)
        except Exception:
            logger.debug("LLM completion failed", exc_info=True)

    # Priority: history → llm → builtins (merge_candidates also sorts by score).
    return merge_candidates([hist, llm, builtins], top_k=top_k)


def complete(
    words: list[str],
    *,
    config: Any | None = None,
    cwd: Any | None = None,
    top_k: int = DEFAULT_TOP_K,
    llm_timeout_s: float = DEFAULT_LLM_TIMEOUT_S,
    use_llm: bool = True,
) -> list[str]:
    """Sync wrapper for shell entrypoints."""

    def _run() -> list[str]:
        return asyncio.run(
            complete_async(
                words,
                config=config,
                cwd=cwd,
                top_k=top_k,
                llm_timeout_s=llm_timeout_s,
                use_llm=use_llm,
            )
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run()

    # Already inside an event loop (e.g. some test runners): use a worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run).result()
