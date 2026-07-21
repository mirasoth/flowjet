"""Interactive ``fj setup`` command for minimal OpenAI-compatible config."""

from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

import yaml

from fj_ai.config import default_config_path

DEFAULT_PROVIDER_NAME = "local"
DEFAULT_PROVIDER_TYPE = "openai"
DEFAULT_API_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_API_KEY = "ollama"
DEFAULT_MODEL = "llama3.2"
DEFAULT_ROUTER_PROFILE = "default"


def run_setup(config_path: str | None = None) -> int:
    """Run interactive setup and write minimal nano.yml values."""
    path = Path(config_path).expanduser() if config_path else default_config_path()
    existing = _load_existing_config(path)

    existing_provider = _find_provider(existing, DEFAULT_PROVIDER_NAME)
    endpoint_default = str(existing_provider.get("api_base_url") or DEFAULT_API_BASE_URL)
    api_key_default = str(existing_provider.get("api_key") or DEFAULT_API_KEY)

    sys.stdout.write(f"Config path: {path}\n")
    endpoint = _prompt_with_default(
        "OpenAI-compatible endpoint (e.g. http://127.0.0.1:11434/v1)",
        endpoint_default,
    )
    api_key = _prompt_secret_with_default("API key", api_key_default)

    sys.stdout.write("Fetching available models...\n")
    try:
        models = fetch_models(endpoint, api_key)
    except RuntimeError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if not models:
        sys.stderr.write("error: no models returned by endpoint\n")
        return 1

    model = choose_model_interactive(models)
    if not model:
        sys.stderr.write("setup cancelled\n")
        return 1

    updated = update_config_for_model(existing, endpoint=endpoint, api_key=api_key, model=model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(updated, sort_keys=False, allow_unicode=True), encoding="utf-8")

    sys.stdout.write(f"Saved config to: {path}\n")
    sys.stdout.write(f"Configured model: {DEFAULT_PROVIDER_NAME}:{model}\n")
    return 0


def fetch_models(endpoint: str, api_key: str, timeout_s: float = 15.0) -> list[str]:
    """Fetch model ids from an OpenAI-compatible endpoint."""
    normalized = endpoint.rstrip("/")
    candidates = [f"{normalized}/models"]
    if not normalized.endswith("/v1"):
        candidates.append(f"{normalized}/v1/models")

    last_error: str | None = None
    for url in candidates:
        req = request.Request(
            url=url,
            method="GET",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            last_error = f"{url} -> HTTP {exc.code}: {body or exc.reason}"
            continue
        except error.URLError as exc:
            last_error = f"{url} -> {exc.reason}"
            continue
        except Exception as exc:  # pragma: no cover - defensive
            last_error = f"{url} -> {type(exc).__name__}: {exc}"
            continue

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            last_error = f"{url} -> invalid JSON: {exc}"
            continue

        data = payload.get("data", []) if isinstance(payload, dict) else []
        models = sorted(
            {
                str(item.get("id", "")).strip()
                for item in data
                if isinstance(item, dict) and str(item.get("id", "")).strip()
            }
        )
        return models

    raise RuntimeError(last_error or "failed to fetch models")


def update_config_for_model(
    existing: dict[str, Any],
    *,
    endpoint: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    """Update only provider/router model basics while preserving other keys."""
    cfg = dict(existing)

    providers = cfg.get("providers")
    if not isinstance(providers, list):
        providers = []
        cfg["providers"] = providers

    provider = _find_provider(cfg, DEFAULT_PROVIDER_NAME)
    if not provider:
        provider = {"name": DEFAULT_PROVIDER_NAME}
        providers.append(provider)

    provider["provider_type"] = DEFAULT_PROVIDER_TYPE
    provider["api_base_url"] = endpoint
    provider["api_key"] = api_key
    provider["models"] = [model]

    router_profiles = cfg.get("router_profiles")
    if not isinstance(router_profiles, list):
        router_profiles = []
        cfg["router_profiles"] = router_profiles

    profile = next(
        (
            item
            for item in router_profiles
            if isinstance(item, dict) and item.get("name") == DEFAULT_ROUTER_PROFILE
        ),
        None,
    )
    if not profile:
        profile = {"name": DEFAULT_ROUTER_PROFILE}
        router_profiles.append(profile)
    profile["router"] = {"default": f"{DEFAULT_PROVIDER_NAME}:{model}"}
    cfg["active_router_profile"] = DEFAULT_ROUTER_PROFILE
    return cfg


def choose_model_interactive(models: list[str], page_size: int = 20) -> str | None:
    """Select one model with paging/filtering for long lists."""
    visible = list(models)
    page = 0
    active_filter = ""

    while True:
        if not visible:
            sys.stdout.write(
                "No models match current filter. Use /text to filter, c to clear, q to cancel.\n"
            )
        else:
            total_pages = (len(visible) - 1) // page_size + 1
            page = min(page, total_pages - 1)
            start = page * page_size
            end = min(len(visible), start + page_size)
            sys.stdout.write(
                f"\nAvailable models ({len(visible)} total"
                + (f", filter='{active_filter}'" if active_filter else "")
                + f"), page {page + 1}/{total_pages}:\n"
            )
            for idx, model in enumerate(visible[start:end], start=start + 1):
                sys.stdout.write(f"  {idx}. {model}\n")

        choice = input(
            "\nSelect number, n/p (page), /text (filter), c (clear), q (cancel): "
        ).strip()

        if not choice:
            continue
        if choice.lower() == "q":
            return None
        if choice.lower() == "n":
            if visible:
                page += 1
            continue
        if choice.lower() == "p":
            if visible:
                page = max(0, page - 1)
            continue
        if choice.lower() == "c":
            visible = list(models)
            active_filter = ""
            page = 0
            continue
        if choice.startswith("/"):
            active_filter = choice[1:].strip().lower()
            visible = (
                [m for m in models if active_filter in m.lower()] if active_filter else list(models)
            )
            page = 0
            continue
        if choice.isdigit():
            selected = int(choice)
            if 1 <= selected <= len(visible):
                return visible[selected - 1]
        sys.stdout.write("Invalid selection. Try again.\n")


def _load_existing_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def _find_provider(config: dict[str, Any], name: str) -> dict[str, Any]:
    providers = config.get("providers", [])
    if not isinstance(providers, list):
        return {}
    for item in providers:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return {}


def _prompt_with_default(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default


def _prompt_secret_with_default(prompt: str, default: str) -> str:
    value = getpass.getpass(f"{prompt} [press Enter to keep current]: ").strip()
    return value or default
