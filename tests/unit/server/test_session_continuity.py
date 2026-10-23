"""Session continuity: checkpointer wiring + ask_user auto-resume.

Covers the fix for stateless server turns (every prompt started a fresh
conversation because the server-surface agent was built without a
checkpointer):

* ``detect_pending_ask_user`` — the shared thread-snapshot probe;
* ``iter_nano_runtime_events`` — a pending ``ask_user`` interrupt turns the
  input text into ``Command(resume={"answers": [text]})`` instead of a new
  ``HumanMessage`` turn;
* ``AgentAdapterBase`` — per-worker checkpointer lifecycle (open once, attach
  at agent build, survive taint rebuilds, close on cleanup, sticky failure);
* ``ModeRoutedSootheAgent`` — ``aget_state`` mode routing + checkpointer
  pass-through.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from flowjet.core.events import RunRequest

pytest.importorskip("langchain_core", reason="nano extra not installed")

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langgraph.types import Command  # noqa: E402

from flowjet.core.bridges.nano.backend import NanoRuntimeBackend  # noqa: E402
from flowjet.core.bridges.nano.interrupts import detect_pending_ask_user  # noqa: E402
from flowjet.core.runtime.isolation.request import IsolatedRunRequest  # noqa: E402

ASK_USER_PENDING = {"type": "ask_user", "questions": [{"question": "Scope?", "header": "Scope"}]}
OTHER_PENDING = {"type": "action_requests", "requests": []}


def message_chunk(message: Any) -> tuple[str, str, Any]:
    return ("ns", "messages", (message, {}))


class ProbeAgent:
    """Stub agent with a controllable ``aget_state`` snapshot."""

    def __init__(self, pending: dict[str, Any] | None = None) -> None:
        self._pending = pending
        self.inputs: list[Any] = []
        self.state_configs: list[Any] = []

    async def aget_state(self, config: Any = None) -> Any:
        self.state_configs.append(config)
        if self._pending is None:
            return None
        entry = SimpleNamespace(value=self._pending)
        task = SimpleNamespace(interrupts=[entry])
        return SimpleNamespace(interrupts=[], tasks=[task])

    async def astream(self, input_arg: Any, **kwargs: Any) -> Any:
        self.inputs.append(input_arg)
        yield message_chunk(AIMessage(content="ok"))


# ---------------------------------------------------------------------------
# detect_pending_ask_user
# ---------------------------------------------------------------------------


async def test_detect_pending_ask_user_no_state_api() -> None:
    agent = SimpleNamespace()  # no aget_state
    assert await detect_pending_ask_user(agent, {"configurable": {"thread_id": "t"}}) is None


async def test_detect_pending_ask_user_soft_fails_on_error() -> None:
    class Boom:
        async def aget_state(self, config: Any = None) -> Any:
            raise RuntimeError("no checkpointer")

    assert await detect_pending_ask_user(Boom(), {"configurable": {"thread_id": "t"}}) is None


async def test_detect_pending_ask_user_root_interrupts() -> None:
    agent = SimpleNamespace(
        aget_state=_async_value(
            SimpleNamespace(interrupts=[SimpleNamespace(value=ASK_USER_PENDING)])
        )
    )
    assert (
        await detect_pending_ask_user(agent, {"configurable": {"thread_id": "t"}})
        is ASK_USER_PENDING
    )


async def test_detect_pending_ask_user_ignores_other_interrupt_types() -> None:
    agent = SimpleNamespace(
        aget_state=_async_value(SimpleNamespace(interrupts=[SimpleNamespace(value=OTHER_PENDING)]))
    )
    assert await detect_pending_ask_user(agent, {"configurable": {"thread_id": "t"}}) is None


def _async_value(value: Any) -> Any:
    async def _get_state(config: Any = None) -> Any:
        return value

    return _get_state


# ---------------------------------------------------------------------------
# iter_nano_runtime_events auto-resume
# ---------------------------------------------------------------------------


async def _run_turn(agent: Any, *, resume_value: Any = None, text: str = "my answer") -> Any:
    backend = NanoRuntimeBackend(agent=agent)
    request = RunRequest(
        model="default",
        input_text=text,
        session="ses_1",
        resume_value=resume_value,
    )
    events = [event async for event in backend.stream_run(request)]
    return events


async def test_pending_ask_user_resumes_with_input_text_as_answer() -> None:
    agent = ProbeAgent(pending=ASK_USER_PENDING)
    await _run_turn(agent)

    assert len(agent.inputs) == 1
    payload = agent.inputs[0]
    assert isinstance(payload, Command)
    assert payload.resume == {"answers": ["my answer"]}
    # The state probe used the same thread the turn runs on.
    assert agent.state_configs[0]["configurable"]["thread_id"] == "ses_1"


async def test_no_pending_interrupt_starts_new_turn() -> None:
    agent = ProbeAgent(pending=None)
    await _run_turn(agent)

    payload = agent.inputs[0]
    assert not isinstance(payload, Command)
    messages = payload["messages"]
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "my answer"


async def test_non_ask_user_interrupt_starts_new_turn() -> None:
    agent = ProbeAgent(pending=OTHER_PENDING)
    await _run_turn(agent)
    assert not isinstance(agent.inputs[0], Command)


async def test_explicit_resume_value_wins_over_auto_detection() -> None:
    agent = ProbeAgent(pending=ASK_USER_PENDING)
    await _run_turn(agent, resume_value={"answers": ["explicit"]})

    payload = agent.inputs[0]
    assert isinstance(payload, Command)
    assert payload.resume == {"answers": ["explicit"]}
    # Explicit resume short-circuits the probe entirely.
    assert agent.state_configs == []


async def test_blank_input_never_resumes() -> None:
    agent = ProbeAgent(pending=ASK_USER_PENDING)
    await _run_turn(agent, text="   ")
    assert not isinstance(agent.inputs[0], Command)


# ---------------------------------------------------------------------------
# AgentAdapterBase checkpointer lifecycle
# ---------------------------------------------------------------------------


class RecordingAgent:
    def __init__(self) -> None:
        self.inputs: list[Any] = []

    async def astream(self, input_arg: Any, **kwargs: Any) -> Any:
        self.inputs.append(input_arg)
        return
        yield  # pragma: no cover - makes this an async generator


def _isolated_request(
    resume_value: Any = None, workspace: Path | None = None
) -> IsolatedRunRequest:
    return IsolatedRunRequest(
        run_id="r1",
        session="ses_1",
        input_text="hi",
        model="default",
        workspace=workspace or Path("."),
        resume_value=resume_value,
    )


def _patch_adapter_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    open_raises: bool = False,
) -> dict[str, Any]:
    """Patch checkpointer opening + agent building; return the recorders."""
    import flowjet.core.agent.workspace as workspace_mod
    import flowjet.core.bridges.base as base_mod

    sentinel_cp = object()
    record: dict[str, Any] = {
        "opened": 0,
        "closed": 0,
        "built": [],
        "cp": sentinel_cp,
    }

    @asynccontextmanager
    async def fake_open(_config: Any) -> Any:
        record["opened"] += 1
        if open_raises:
            raise RuntimeError("sqlite unavailable")
        yield sentinel_cp
        record["closed"] += 1

    monkeypatch.setattr(workspace_mod.Checkpointers, "open", fake_open)

    def fake_create(_config_path: Any = None, **kwargs: Any) -> Any:
        record["built"].append(kwargs)
        return RecordingAgent()

    monkeypatch.setattr(base_mod, "create_server_agent_instance", fake_create)
    return record


async def test_adapter_opens_checkpointer_once_and_attaches_to_builds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from flowjet.core.bridges.nano.adapter import NanoAgentAdapter

    record = _patch_adapter_env(monkeypatch, tmp_path)
    adapter = NanoAgentAdapter(
        config_path=str(tmp_path / "missing.yml"), checkpointer_policy="auto"
    )

    events = [event async for event in adapter.astream(_isolated_request(workspace=tmp_path))]
    assert events  # RunCompleted present
    assert record["opened"] == 1
    assert record["built"][0]["checkpointer"] is record["cp"]

    # Taint-recycle rebuilds the agent but reuses the open checkpointer.
    adapter._tainted = True
    adapter.prepare_for_request()
    events = [event async for event in adapter.astream(_isolated_request(workspace=tmp_path))]
    assert events
    assert record["opened"] == 1
    assert len(record["built"]) == 2
    assert record["built"][1]["checkpointer"] is record["cp"]

    # Cleanup closes the checkpointer; the next build reopens it.
    await adapter.cleanup()
    assert record["closed"] == 1
    events = [event async for event in adapter.astream(_isolated_request(workspace=tmp_path))]
    assert events
    assert record["opened"] == 2


async def test_adapter_policy_off_never_opens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from flowjet.core.bridges.nano.adapter import NanoAgentAdapter

    record = _patch_adapter_env(monkeypatch, tmp_path)
    adapter = NanoAgentAdapter(config_path=str(tmp_path / "missing.yml"))

    events = [event async for event in adapter.astream(_isolated_request(workspace=tmp_path))]
    assert events
    assert record["opened"] == 0
    assert record["built"][0]["checkpointer"] is None


async def test_adapter_checkpointer_failure_is_sticky_and_non_fatal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from flowjet.core.bridges.nano.adapter import NanoAgentAdapter

    record = _patch_adapter_env(monkeypatch, tmp_path, open_raises=True)
    adapter = NanoAgentAdapter(
        config_path=str(tmp_path / "missing.yml"), checkpointer_policy="auto"
    )

    events = [event async for event in adapter.astream(_isolated_request(workspace=tmp_path))]
    assert events
    assert record["built"][0]["checkpointer"] is None

    adapter._tainted = True
    adapter.prepare_for_request()
    events = [event async for event in adapter.astream(_isolated_request(workspace=tmp_path))]
    assert events
    # The failed open is not retried on every build.
    assert record["opened"] == 1


async def test_adapter_forwards_request_resume_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from flowjet.core.bridges.nano.adapter import NanoAgentAdapter

    _patch_adapter_env(monkeypatch, tmp_path)
    adapter = NanoAgentAdapter(
        config_path=str(tmp_path / "missing.yml"), checkpointer_policy="auto"
    )

    events = [
        event
        async for event in adapter.astream(
            _isolated_request(resume_value={"answers": ["x"]}, workspace=tmp_path)
        )
    ]
    assert events
    agent = adapter._agent
    assert isinstance(agent.inputs[0], Command)
    assert agent.inputs[0].resume == {"answers": ["x"]}


# ---------------------------------------------------------------------------
# ModeRoutedSootheAgent
# ---------------------------------------------------------------------------


class _FakeModeAgent:
    def __init__(self) -> None:
        self.checkpointer = None

    async def aget_state(self, config: Any = None) -> Any:
        return SimpleNamespace(interrupts=[SimpleNamespace(value=ASK_USER_PENDING)])


async def test_mode_routed_soothe_agent_routes_state_and_passes_checkpointer() -> None:
    from flowjet.core.agent.factory import ModeRoutedSootheAgent

    builds: list[dict[str, Any]] = []

    def factory(_config: Any, **kwargs: Any) -> _FakeModeAgent:
        builds.append(kwargs)
        return _FakeModeAgent()

    cp = object()
    routed = ModeRoutedSootheAgent(object(), factory, sandbox=None, checkpointer=cp)

    snapshot = await routed.aget_state(
        {"configurable": {"thread_id": "t", "interaction_mode": "ask"}}
    )
    assert snapshot is not None
    # The state read routed through the ask-mode agent, built with the
    # shared checkpointer.
    assert builds[0]["interaction_mode"] == "ask"
    assert builds[0]["checkpointer"] is cp

    # Default (no mode in config) routes to the agent graph.
    await routed.aget_state({"configurable": {"thread_id": "t"}})
    assert builds[1]["interaction_mode"] == "agent"
