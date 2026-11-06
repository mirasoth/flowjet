"""Token-usage accounting for the soothe-nano bridge.

FlowJet drives ``SootheNanoAgent.astream`` directly (both the ``nano`` and the
``soothe`` host CoreAgent backends). Providers attach the real token breakdown
to the final ``AIMessage``/``AIMessageChunk`` of each generation as
``usage_metadata`` (LangChain) or ``response_metadata.token_usage`` (OpenAI).
This module collects those counts across the whole run so the CLI can print an
authoritative total in its final ``✓ Done`` footer.

The accounting mirrors soothe's optimized TUI/daemon path (v1.2.7,
``fix(tui): show token usage live with correct and complete breakdown``):

* **Sum streamed usage deltas per generation, not last-wins.** Streaming
  providers split one generation's input/output/cache counts across several
  chunks; taking the last chunk drops earlier tokens. Counts are summed.
* **Dedupe by generation id.** The same ``usage_metadata`` is often repeated on
  every chunk of a generation (and the full message replays at the end). A
  per-message-id map keeps one authoritative breakdown per generation instead
  of double-counting replays, while id-less chunks are summed linearly.
* **Actual-first, estimate-on-demand.** When a provider reports no usage at
  all, fall back to soothe-nano's unified model-aware
  :func:`estimate_token_usage` (IG-761) over the collected messages — which
  counts *both* input and output plus per-message structural overhead — so the
  footer still reflects real consumption instead of silently showing nothing.

The accumulator is deliberately transport-agnostic: it consumes the already
parsed ``(namespace, mode, data)`` stream chunks, so the CLI, ACP and OpenAI
projections all receive the same totals through ``RunCompleted.usage``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Keys summed field-wise. ``cache_*`` stay a subset of input (they are not
# added to the total a second time) but are carried for richer clients.
_SUM_KEYS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
)

# LangChain usage_metadata / OpenAI response_metadata token_usage aliases.
_INPUT_ALIASES = ("input_tokens", "prompt_tokens")
_OUTPUT_ALIASES = ("output_tokens", "completion_tokens")


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _first_int(usage: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        if key in usage:
            return _as_int(usage.get(key))
    return 0


def _cache_counts(usage: dict[str, Any]) -> tuple[int, int]:
    """Return ``(cache_read, cache_creation)`` from provider detail blocks."""
    read = _as_int(usage.get("cache_read_input_tokens"))
    creation = _as_int(usage.get("cache_creation_input_tokens"))
    details = usage.get("input_token_details")
    if isinstance(details, dict):
        read = read or _as_int(details.get("cache_read"))
        creation = creation or _as_int(details.get("cache_creation"))
    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        read = read or _as_int(prompt_details.get("cached_tokens"))
    return read, creation


def _normalize(usage: dict[str, Any]) -> dict[str, int]:
    """Normalize a LangChain/OpenAI usage mapping into a full breakdown."""
    input_toks = _first_int(usage, _INPUT_ALIASES)
    output_toks = _first_int(usage, _OUTPUT_ALIASES)
    total_toks = _as_int(usage.get("total_tokens")) or input_toks + output_toks
    read, creation = _cache_counts(usage)
    return {
        "input_tokens": input_toks,
        "output_tokens": output_toks,
        "total_tokens": total_toks,
        "cache_read_tokens": read,
        "cache_creation_tokens": creation,
    }


@dataclass(frozen=True, slots=True)
class UsageBreakdown:
    """Full per-run token breakdown (cache stays a subset of input)."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def has_any(self) -> bool:
        return any(
            (
                self.input_tokens,
                self.output_tokens,
                self.total_tokens,
                self.cache_read_tokens,
                self.cache_creation_tokens,
            )
        )


def extract_usage(message: Any) -> dict[str, int] | None:
    """Return a normalized usage breakdown from a streamed message, else None.

    Handles LangChain ``usage_metadata``, OpenAI ``response_metadata``
    (``token_usage`` / ``usage``), and flat wire dicts carrying either shape —
    the same three provider shapes soothe's daemon coalescer preserves.
    """
    if message is None:
        return None

    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        return _normalize(usage)

    response = getattr(message, "response_metadata", None)
    if isinstance(response, dict):
        for key in ("token_usage", "usage"):
            nested = response.get(key)
            if isinstance(nested, dict) and nested:
                return _normalize(nested)

    if isinstance(message, dict):
        holders = [message]
        data = message.get("data")
        if isinstance(data, dict):
            holders.append(data)
        for holder in holders:
            direct = holder.get("usage_metadata")
            if isinstance(direct, dict) and direct:
                return _normalize(direct)
            resp = holder.get("response_metadata")
            if isinstance(resp, dict):
                for key in ("token_usage", "usage"):
                    nested = resp.get(key)
                    if isinstance(nested, dict) and nested:
                        return _normalize(nested)
    return None


def _merge(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {key: _as_int(a.get(key)) + _as_int(b.get(key)) for key in _SUM_KEYS}


class TokenUsageAccumulator:
    """Sum usage deltas across a run, deduped by generation id.

    ``observe`` folds one ``messages``-mode stream chunk. ``snapshot`` returns
    the cumulative :class:`UsageBreakdown`, or ``None`` when no provider usage
    was seen (the caller then falls back to estimation).
    """

    def __init__(self) -> None:
        # One authoritative breakdown per generation id (replays overwrite, not
        # add). Id-less chunks cannot be deduped, so they are summed linearly.
        self._by_id: dict[str, dict[str, int]] = {}
        self._anonymous: list[dict[str, int]] = []

    def observe(self, chunk: Any) -> None:
        """Fold usage from a ``(namespace, mode, data)`` stream chunk."""
        if not isinstance(chunk, (tuple, list)) or len(chunk) != 3:
            return
        _namespace, mode, data = chunk
        if mode != "messages":
            return
        if not isinstance(data, (tuple, list)) or not data:
            return
        message = data[0]

        breakdown = extract_usage(message)
        if breakdown is None:
            return
        msg_id = getattr(message, "id", None)
        if msg_id is None and isinstance(message, dict):
            msg_id = message.get("id")
        if msg_id:
            # Sum deltas for this generation: streaming providers split the
            # breakdown across chunks sharing one id (input on an early chunk,
            # output on a later one). Last-wins would drop the earlier half.
            existing = self._by_id.get(str(msg_id))
            self._by_id[str(msg_id)] = (
                _merge(existing, breakdown) if existing is not None else breakdown
            )
        else:
            self._anonymous.append(breakdown)

    def snapshot(self) -> UsageBreakdown | None:
        """Return the summed breakdown, or ``None`` when no usage was seen."""
        parts = list(self._by_id.values()) + self._anonymous
        if not parts:
            return None
        total: dict[str, int] = {key: 0 for key in _SUM_KEYS}
        for part in parts:
            total = _merge(total, part)
        return UsageBreakdown(**total) if any(total.values()) else None

    def estimate(self, messages: list[Any], *, model: str | None = None) -> UsageBreakdown:
        """Estimate usage over ``messages`` via soothe-nano's unified API.

        Only called when no provider reported usage. ``estimate_token_usage`` is
        actual-first itself, but here it operates purely on the estimation path
        (it counts input + output with model-aware tokenization and per-message
        structural overhead). The caller passes a *clean* reconstructed
        conversation (one final AI message per generation), never the raw
        cumulative stream chunks, so estimation cannot double-count replays.
        A missing/old soothe-nano degrades to zero rather than breaking the run.
        """
        try:
            from soothe_nano.utils.token_usage import estimate_token_usage

            result = estimate_token_usage(messages, model=model)
        except Exception:  # noqa: BLE001 - estimation must never break a run
            return UsageBreakdown()
        return UsageBreakdown(
            input_tokens=_as_int(result.get("input_tokens")),
            output_tokens=_as_int(result.get("output_tokens")),
            total_tokens=_as_int(result.get("total_tokens")),
        )


__all__ = ["TokenUsageAccumulator", "UsageBreakdown", "extract_usage"]
