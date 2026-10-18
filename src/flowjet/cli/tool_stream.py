"""Tool-arg accumulation now lives in ``flowjet.core.streaming.tool_stream``.

Kept as a re-export so the CLI renderer and its tests keep their import paths.
"""

from __future__ import annotations

from flowjet.core.streaming.tool_stream import (
    PartialArgsParser,
    ToolCallArgAccumulator,
)

parse_partial_args = PartialArgsParser.parse
_as_chunk_dict = ToolCallArgAccumulator._as_chunk_dict
_merge_args = ToolCallArgAccumulator._merge_args

__all__ = [
    "PartialArgsParser",
    "ToolCallArgAccumulator",
    "_as_chunk_dict",
    "_merge_args",
    "parse_partial_args",
]
