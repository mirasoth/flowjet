"""Unit tests for fj setup command helpers."""

from __future__ import annotations

from typing import Any

from fj_ai.setup_cmd import DEFAULT_PROVIDER_NAME, choose_model_interactive, update_config_for_model


def test_update_config_for_model_preserves_unrelated_keys() -> None:
    existing: dict[str, Any] = {
        "providers": [
            {
                "name": "local",
                "provider_type": "openai",
                "api_base_url": "http://old/v1",
                "api_key": "old",
                "models": ["old-model"],
            },
            {"name": "other", "provider_type": "openai"},
        ],
        "tools": {"wizsearch": {"enabled": False}},
        "persistence": {"default_backend": "sqlite"},
    }
    updated = update_config_for_model(
        existing,
        endpoint="http://127.0.0.1:11434/v1",
        api_key="ollama",
        model="llama3.2",
    )

    local_provider = next(p for p in updated["providers"] if p["name"] == DEFAULT_PROVIDER_NAME)
    assert local_provider["api_base_url"] == "http://127.0.0.1:11434/v1"
    assert local_provider["api_key"] == "ollama"
    assert local_provider["models"] == ["llama3.2"]
    assert updated["tools"] == {"wizsearch": {"enabled": False}}
    assert updated["persistence"] == {"default_backend": "sqlite"}
    assert updated["active_router_profile"] == "default"


def test_choose_model_interactive_select_number(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    answers = iter(["2"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    selected = choose_model_interactive(["a", "b", "c"])
    assert selected == "b"


def test_choose_model_interactive_filter_then_select(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    answers = iter(["/llama", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    selected = choose_model_interactive(["gpt-4o", "llama3.2", "qwen2.5"])
    assert selected == "llama3.2"
