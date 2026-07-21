"""Unit tests for thread listing."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from fj_ai.threads import (
    ThreadInfo,
    format_thread_list,
    latest_thread_id,
    list_threads,
    preview_user_request,
    simplify_timestamp,
)


def test_simplify_timestamp_to_seconds() -> None:
    assert simplify_timestamp("2026-07-21T08:57:45.236018+00:00") == "2026-07-21 08:57:45"
    assert simplify_timestamp("2026-07-21T08:57:45Z") == "2026-07-21 08:57:45"
    assert simplify_timestamp(None) is None


def test_preview_user_request_first_human() -> None:
    preview = preview_user_request(
        [HumanMessage(content="hello world"), AIMessage(content="hi")],
        limit=20,
    )
    assert preview == "hello world"


def test_preview_user_request_truncates() -> None:
    preview = preview_user_request([HumanMessage(content="x" * 100)], limit=10)
    assert preview is not None
    assert len(preview) == 10
    assert preview.endswith("…")


def test_format_thread_list_empty() -> None:
    assert format_thread_list([]) == ""


def test_format_thread_list_columns() -> None:
    text = format_thread_list(
        [
            ThreadInfo("fj-short", "2026-07-21 10:00:00", "hello"),
            ThreadInfo("fj-longer-id", "2026-07-20 09:00:00", None),
        ]
    )
    lines = text.strip().splitlines()
    assert lines[0].startswith("fj-short")
    assert "2026-07-21 10:00:00" in lines[0]
    assert lines[0].endswith("hello")
    assert "fj-longer-id" in lines[1]
    assert "2026-07-20 09:00:00" in lines[1]


@pytest.mark.asyncio
async def test_list_threads_none_checkpointer() -> None:
    assert await list_threads(None) == []


@pytest.mark.asyncio
async def test_latest_thread_id_none_checkpointer() -> None:
    assert await latest_thread_id(None) is None


@pytest.mark.asyncio
async def test_latest_thread_id_returns_newest() -> None:
    class FakeConn:
        def execute(self, _query: str):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        async def fetchone(self):
            return ("fj-newest",)

    class FakeCp:
        conn = FakeConn()

    assert await latest_thread_id(FakeCp()) == "fj-newest"


@pytest.mark.asyncio
async def test_latest_thread_id_empty() -> None:
    class FakeConn:
        def execute(self, _query: str):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        async def fetchone(self):
            return None

    class FakeCp:
        conn = FakeConn()

    assert await latest_thread_id(FakeCp()) is None


@pytest.mark.asyncio
async def test_list_threads_orders_newest_first() -> None:
    class FakeConn:
        def __init__(self) -> None:
            self._query = ""
            self._params: tuple[object, ...] = ()

        def execute(self, query: str, params: tuple[object, ...] = ()):
            self._query = query
            self._params = params
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

        async def fetchall(self):
            q = self._query
            if "MAX(checkpoint_id)" in q and "c.checkpoint" in q:
                return [
                    ("fj-new", "cp-2", "msgpack", b"new"),
                    ("fj-old", "cp-1", "msgpack", b"old"),
                ]
            if "MIN(checkpoint_id)" in q:
                return [
                    ("fj-new", "cp-0", 0, "msgpack", b"new-msg"),
                    ("fj-old", "cp-0", 0, "msgpack", b"old-msg"),
                ]
            if "LIMIT ?" in q:
                lim = int(self._params[0])  # type: ignore[index]
                rows = [("fj-new",), ("fj-old",)]
                return rows[:lim]
            return [("fj-new",), ("fj-old",)]

    class FakeSerde:
        def loads_typed(self, data: tuple[str, bytes]) -> object:
            _type, blob = data
            if blob == b"new":
                return {"ts": "2026-07-21T12:00:00.123456+00:00"}
            if blob == b"old":
                return {"ts": "2026-07-20T12:00:00.999999+00:00"}
            if blob == b"new-msg":
                return [HumanMessage(content="latest question")]
            if blob == b"old-msg":
                return [HumanMessage(content="older question")]
            return {}

    class FakeCp:
        conn = FakeConn()
        serde = FakeSerde()

    threads = await list_threads(FakeCp())
    assert [t.thread_id for t in threads] == ["fj-new", "fj-old"]
    assert threads[0].updated_at == "2026-07-21 12:00:00"
    assert threads[0].preview == "latest question"
    assert threads[1].preview == "older question"

    limited = await list_threads(FakeCp(), limit=1)
    assert [t.thread_id for t in limited] == ["fj-new"]
