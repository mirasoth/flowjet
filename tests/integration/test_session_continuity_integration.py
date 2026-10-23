"""Integration: session continuity via checkpointer + ask_user auto-resume.

Real end-to-end coverage of the stateless-turn fix — a real nano agent graph,
a real ``interrupt()`` inside an ask_user-style tool, a real sqlite
checkpointer on disk, all driven through the same ``NanoRuntimeBackend``
stream path the ACP server uses:

* Turn 1 pauses on ``ask_user`` — the pause is checkpointed, the turn ends
  with ``InterruptWaiting`` (``end_turn`` semantics unchanged).
* Turn 2 arrives on a **different agent instance with its own sqlite
  connection** (what a pool worker / restart looks like) and the input text
  is delivered as the answer via ``Command(resume=...)`` — no new turn, no
  second question, and the model still sees the full conversation history.
* Turn 3 starts a fresh turn (no pending interrupt) and still sees history —
  a stateless agent would ask again.
* A second session on the same store stays isolated (its own thread).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("soothe_nano", reason="nano extra not installed")

from langchain_core.callbacks import CallbackManagerForLLMRun  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, BaseMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.types import interrupt  # noqa: E402

from flowjet.core.bridges.nano.backend import NanoRuntimeBackend  # noqa: E402
from flowjet.core.events import (  # noqa: E402
    InterruptWaiting,
    RunCompleted,
    RunFailed,
    RunRequest,
)

pytestmark = pytest.mark.integration


class AskFirstScriptedModel(BaseChatModel):
    """Ask once, then finish: tool call → (interrupt/resume) → final answer.

    The final answer embeds the tool result and the message count, so tests
    can assert both the resume payload and the surviving history.
    """

    @property
    def _llm_type(self) -> str:
        return "ask-first-scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> AskFirstScriptedModel:  # type: ignore[override]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        last = messages[-1] if messages else None
        if type(last).__name__ == "ToolMessage":
            content = f"final|{last.content}|msgs={len(messages)}"
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])
        asked = any(getattr(m, "tool_calls", None) for m in messages if isinstance(m, AIMessage))
        if asked:
            # History exists but no fresh tool result: a plain continuation.
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="final|continue"))]
            )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {"name": "ask", "args": {"question": "What scope?"}, "id": "call_1"}
                        ],
                    )
                )
            ]
        )


@tool
def ask(question: str) -> str:
    """Mirror of soothe's ``ask_user``: pause the graph for the user's answer."""
    payload = interrupt(
        {"type": "ask_user", "questions": [{"question": question, "header": "Scope"}]}
    )
    answers = payload.get("answers") if isinstance(payload, dict) else None
    first = answers[0] if isinstance(answers, list) and answers else "(no answer)"
    return f"answered: {first}"


@pytest.fixture
def continuity_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated soothe home + data dir; no real keys, no real config."""
    home = tmp_path / ".soothe"
    (home / "data").mkdir(parents=True)
    (home / "config").mkdir(parents=True)
    monkeypatch.setenv("SOOTHE_HOME", str(home))
    monkeypatch.setenv("SOOTHE_DATA_DIR", str(home / "data"))
    monkeypatch.setenv("FLOWJET_HOME", str(home))
    # soothe_nano.paths freezes SOOTHE_DATA_DIR as a module-level constant at
    # import (collection) time — in-process env changes alone are ignored, so
    # patch the constant too or the checkpointer lands in the real home.
    import soothe_nano.paths as nano_paths

    monkeypatch.setattr(nano_paths, "SOOTHE_DATA_DIR", str(home / "data"))
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DASHSCOPE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    # Every config-resolved role (orchestration, planner, ...) must use the
    # scripted model — no network, no litellm.
    from soothe_nano.config import SootheConfig

    monkeypatch.setattr(
        SootheConfig,
        "create_chat_model",
        lambda self, role="default", **kw: AskFirstScriptedModel(),
    )
    return home


def _build_agent(checkpointer: Any) -> Any:
    from soothe_nano import create_nano_agent
    from soothe_nano.config import SootheConfig

    return create_nano_agent(
        SootheConfig(), model=AskFirstScriptedModel(), tools=[ask], checkpointer=checkpointer
    )


async def _run_turn(agent: Any, text: str, session: str) -> list[Any]:
    backend = NanoRuntimeBackend(agent=agent)
    return [
        event
        async for event in backend.stream_run(
            RunRequest(model="default", input_text=text, session=session)
        )
    ]


def _completed_output(events: list[Any]) -> str:
    outs = [e.output_text for e in events if isinstance(e, RunCompleted)]
    assert len(outs) == 1, f"expected exactly one RunCompleted, got {len(outs)}"
    return outs[0]


def _assert_no_failures(events: list[Any]) -> None:
    failures = [e for e in events if isinstance(e, RunFailed)]
    assert not failures, f"run failed: {failures[0].message}"


async def test_ask_user_pause_is_checkpointed_and_resumed_across_instances(
    continuity_env: Path,
) -> None:
    """The regression this file guards: server turns used to be stateless.

    Turn 1 asks; turn 2 — on a brand-new agent + sqlite connection, like a
    different pool worker — must resume with the input text as the answer
    instead of starting a fresh conversation.
    """
    from soothe_nano.config import SootheConfig

    from flowjet.core.agent.workspace import Checkpointers

    config = SootheConfig()

    # --- Turn 1: pause on ask_user, checkpointed. ---
    async with Checkpointers.open(config) as cp1:
        assert cp1 is not None, "sqlite checkpointer expected for default config"
        agent1 = _build_agent(cp1)
        events1 = await _run_turn(agent1, "design a study", "ses_cont")

    _assert_no_failures(events1)
    waiting = [e for e in events1 if isinstance(e, InterruptWaiting)]
    assert waiting, f"turn 1 should pause on ask_user, got {[type(e).__name__ for e in events1]}"
    questions = waiting[0].questions
    assert questions and questions[0].get("question") == "What scope?"
    _completed_output(events1)  # end_turn semantics: the turn completes.

    # The pause survives on disk (what a worker restart / rebuild sees).
    db = continuity_env / "data" / "databases" / "checkpoints.db"
    assert db.is_file(), "checkpointer db must live on the shared data dir"

    # --- Turn 2: fresh agent + fresh connection, same session → resume. ---
    async with Checkpointers.open(config) as cp2:
        agent2 = _build_agent(cp2)
        events2 = await _run_turn(agent2, "blue", "ses_cont")

    _assert_no_failures(events2)
    assert not [e for e in events2 if isinstance(e, InterruptWaiting)], (
        "turn 2 must resume the paused ask_user, not ask again"
    )
    output2 = _completed_output(events2)
    assert "answered: blue" in output2, (
        f"the input text must be delivered as the ask_user answer, got {output2!r}"
    )
    # History survived across instances: the model saw the earlier turns.
    assert "msgs=" in output2

    # --- Turn 3: fresh turn (nothing pending), history still intact. ---
    async with Checkpointers.open(config) as cp3:
        agent3 = _build_agent(cp3)
        events3 = await _run_turn(agent3, "anything else", "ses_cont")

    _assert_no_failures(events3)
    assert not [e for e in events3 if isinstance(e, InterruptWaiting)], (
        "with no pending interrupt the turn must start normally — but a stateless "
        "agent would have asked again here"
    )
    output3 = _completed_output(events3)
    assert "final|" in output3


async def test_sessions_are_isolated_threads(continuity_env: Path) -> None:
    """A second session gets a fresh thread: it asks even though another
    session on the same store is mid-pause."""
    from soothe_nano.config import SootheConfig

    from flowjet.core.agent.workspace import Checkpointers

    config = SootheConfig()
    async with Checkpointers.open(config) as cp:
        agent = _build_agent(cp)
        first = await _run_turn(agent, "design a study", "ses_a")
        other = await _run_turn(agent, "design a study", "ses_b")

    _assert_no_failures(first)
    _assert_no_failures(other)
    assert [e for e in first if isinstance(e, InterruptWaiting)]
    assert [e for e in other if isinstance(e, InterruptWaiting)], (
        "the second session must have its own thread state"
    )
