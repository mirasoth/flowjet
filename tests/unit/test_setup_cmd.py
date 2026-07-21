"""Unit tests for fj setup command helpers."""

from __future__ import annotations

from typing import Any

from fj_ai.setup_cmd import (
    DEFAULT_NEW_PROVIDER_NAME,
    DEFAULT_PROVIDER_NAME,
    _parse_model_filter,
    _prompt_secret_with_default,
    choose_model_interactive,
    choose_provider_interactive,
    suggest_provider_name,
    update_config_for_model,
)


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
        provider_name="local",
        endpoint="http://127.0.0.1:11434/v1",
        api_key="ollama",
        model="llama3.2",
    )

    local_provider = next(p for p in updated["providers"] if p["name"] == DEFAULT_PROVIDER_NAME)
    assert local_provider["api_base_url"] == "http://127.0.0.1:11434/v1"
    assert local_provider["api_key"] == "ollama"
    assert local_provider["models"] == ["llama3.2", "old-model"]
    assert updated["tools"] == {"wizsearch": {"enabled": False}}
    assert updated["persistence"] == {"default_backend": "sqlite"}
    assert updated["active_router_profile"] == "default"
    assert updated["router_profiles"][0]["router"]["default"] == "local:llama3.2"


def test_update_config_adds_default_new_provider_name() -> None:
    updated = update_config_for_model(
        {},
        endpoint="http://127.0.0.1:11434/v1",
        api_key="ollama",
        model="llama3.2",
    )
    assert updated["providers"][0]["name"] == DEFAULT_NEW_PROVIDER_NAME
    assert updated["router_profiles"][0]["router"]["default"] == "fj-ai-default:llama3.2"
    assert updated["active_router_profile"] == "default"


def test_update_config_uses_provider_prefix_and_activates_current_profile() -> None:
    existing: dict[str, Any] = {
        "providers": [
            {
                "name": "dashscope",
                "provider_type": "openai",
                "api_base_url": "https://dashscope.example/v1",
                "api_key": "${DASHSCOPE_API_KEY}",
                "models": ["glm-5.2"],
            }
        ],
        "router_profiles": [
            {
                "name": "production",
                "router": {
                    "default": "dashscope:glm-5.2",
                    "fast": "dashscope:qwen3.6-flash",
                    "think": "dashscope:glm-5.2",
                },
            },
            {"name": "default", "router": {"default": "local:llama3.2"}},
        ],
        "active_router_profile": "production",
    }
    updated = update_config_for_model(
        existing,
        provider_name="coding-dashscope",
        endpoint="https://coding.dashscope.aliyuncs.com/v1",
        api_key="sk-test",
        model="qwen3.7-plus",
    )

    names = [p["name"] for p in updated["providers"]]
    assert names == ["dashscope", "coding-dashscope"]
    coding = next(p for p in updated["providers"] if p["name"] == "coding-dashscope")
    assert coding["models"] == ["qwen3.7-plus"]
    assert updated["active_router_profile"] == "production"

    production = next(p for p in updated["router_profiles"] if p["name"] == "production")
    assert production["router"]["default"] == "coding-dashscope:qwen3.7-plus"
    # Preserve sibling router roles.
    assert production["router"]["fast"] == "dashscope:qwen3.6-flash"
    assert production["router"]["think"] == "dashscope:glm-5.2"


def test_suggest_provider_name_from_endpoint() -> None:
    assert suggest_provider_name("http://127.0.0.1:11434/v1") == "fj-ai-default"
    assert suggest_provider_name("https://coding.dashscope.aliyuncs.com/v1") == "coding-dashscope"
    assert suggest_provider_name("https://apihub.agnes-ai.com/v1") == "apihub-agnes-ai"
    assert suggest_provider_name("http://100.75.70.86:9642/v1") == "host-100-75-70-86"


def test_choose_provider_interactive_select_existing(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    providers = [
        {"name": "dashscope", "api_base_url": "https://a/v1", "models": ["m1"]},
        {"name": "local", "api_base_url": "http://127.0.0.1:11434/v1", "models": ["llama"]},
    ]
    monkeypatch.setattr("builtins.input", lambda _prompt: "1")
    selected = choose_provider_interactive(providers)
    assert selected == providers[0]
    out = capsys.readouterr().out
    assert "dashscope" in out
    assert "Add new provider" in out


def test_choose_provider_interactive_add_new(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    providers = [{"name": "dashscope", "api_base_url": "https://a/v1", "models": ["m1"]}]
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")
    assert choose_provider_interactive(providers) == {}


def test_choose_provider_interactive_default_is_add_new(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    providers = [{"name": "dashscope", "api_base_url": "https://a/v1", "models": ["m1"]}]
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert choose_provider_interactive(providers) == {}


def test_choose_provider_interactive_cancel(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    providers = [{"name": "dashscope", "api_base_url": "https://a/v1", "models": ["m1"]}]
    monkeypatch.setattr("builtins.input", lambda _prompt: "q")
    assert choose_provider_interactive(providers) is None


def test_choose_provider_interactive_empty_adds_new() -> None:
    assert choose_provider_interactive([]) == {}


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


def test_choose_model_interactive_text_prefix_filter(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    answers = iter(["/text qwen3.7", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    selected = choose_model_interactive(
        ["glm-5", "qwen3.6-plus", "qwen3.7-plus", "kimi-k2.5"],
    )
    assert selected == "qwen3.7-plus"


def test_parse_model_filter() -> None:
    assert _parse_model_filter("/qwen3.7") == "qwen3.7"
    assert _parse_model_filter("/text qwen3.7") == "qwen3.7"
    assert _parse_model_filter("/filter Qwen") == "qwen"
    assert _parse_model_filter("/") == ""


def test_prompt_secret_shows_masked_default(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    seen: list[str] = []

    def fake_read(prompt: str) -> str:
        seen.append(prompt)
        return ""

    monkeypatch.setattr("fj_ai.setup_cmd._read_secret_masked", fake_read)
    assert _prompt_secret_with_default("API key", "secret-value") == "secret-value"
    assert seen == ["API key [****]: "]


def test_prompt_secret_uses_entered_value(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("fj_ai.setup_cmd._read_secret_masked", lambda _prompt: "new-key")
    assert _prompt_secret_with_default("API key", "old") == "new-key"


def test_choose_model_interactive_eof_cancels(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    def boom(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)
    assert choose_model_interactive(["a", "b"]) is None


def test_run_setup_keyboard_interrupt_is_clean(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    from fj_ai.setup_cmd import run_setup

    def boom(_config_path: str | None = None) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr("fj_ai.setup_cmd._run_setup", boom)
    assert run_setup() == 130
    assert "setup cancelled" in capsys.readouterr().err
