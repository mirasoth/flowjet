"""Stream presentation: tool-result interpretation and tool-arg accumulation.

Shared by the nano→event mapper (:mod:`flowjet.core.bridges.nano.mapping`),
the CLI renderer and protocol projections. Nothing here drives an agent —
these are the presentation-side pieces of the runtime event pipeline.
"""

from flowjet.core.streaming.presentation import (
    AiTextExtractor,
    OutputTextChunker,
    StepProgressFormatter,
    ToolCallSummarizer,
)
from flowjet.core.streaming.tool_results import ToolResultInspector
from flowjet.core.streaming.tool_stream import (
    PartialArgsParser,
    ToolCallArgAccumulator,
)

__all__ = [
    "AiTextExtractor",
    "OutputTextChunker",
    "PartialArgsParser",
    "StepProgressFormatter",
    "ToolCallArgAccumulator",
    "ToolCallSummarizer",
    "ToolResultInspector",
]
