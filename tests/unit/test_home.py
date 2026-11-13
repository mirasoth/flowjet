"""Unit tests for ``flowjet.home`` — config-path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from flowjet.core.agent.config import FlowJetConfigLoader
from flowjet.core.backend_config import Backend
from flowjet.home import (
    DEFAULT_FLOWJET_HOME,
    default_config_path,
    flowjet_home,
)

load_config = FlowJetConfigLoader.load

_NANO_YML = """
providers:
  - name: local
    provider_type: openai
    api_base_url: "http://127.0.0.1:9/v1"
    api_key: local
    models: [test-model]
router_profiles:
  - name: default
    router:
      default: "local:test-model"
active_router_profile: default
"""


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_flowjet_home_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLOWJET_HOME", raising=False)
    assert flowjet_home() == Path(DEFAULT_FLOWJET_HOME).expanduser()
    assert flowjet_home() == Path.home() / ".flowjet"


def test_flowjet_home_reads_env_at_call_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FLOWJET_HOME", raising=False)
    assert flowjet_home() != tmp_path
    monkeypatch.setenv("FLOWJET_HOME", str(tmp_path))
    assert flowjet_home() == tmp_path


def test_flowjet_home_expands_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOWJET_HOME", "~/custom-flowjet")
    assert flowjet_home() == Path.home() / "custom-flowjet"


def test_flowjet_home_empty_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOWJET_HOME", "")
    assert flowjet_home() == Path.home() / ".flowjet"


def test_default_config_path_uses_flowjet_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FLOWJET_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "config" / "nano.yml"


def test_default_config_path_ignores_soothe_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: SOOTHE_HOME must not affect the config path."""
    monkeypatch.setenv("FLOWJET_HOME", str(tmp_path / "flowjet"))
    monkeypatch.setenv("SOOTHE_HOME", str(tmp_path / "soothe"))
    assert default_config_path() == tmp_path / "flowjet" / "config" / "nano.yml"


def test_default_config_path_does_no_io(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Called by argparse help builders, so it must not touch the filesystem."""
    monkeypatch.setenv("FLOWJET_HOME", str(tmp_path / "nope"))
    assert default_config_path().name == "nano.yml"
    assert not (tmp_path / "nope").exists()


# ---------------------------------------------------------------------------
# load_config integration
# ---------------------------------------------------------------------------


def test_load_config_explicit_path_loads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "flowjet"
    monkeypatch.setenv("FLOWJET_HOME", str(target))

    explicit = tmp_path / "explicit.yml"
    explicit.write_text(_NANO_YML, encoding="utf-8")
    config = load_config(explicit, backend=Backend.NANO)

    assert config.active_router_profile == "default"


def test_load_config_missing_explicit_path_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "flowjet"
    monkeypatch.setenv("FLOWJET_HOME", str(target))

    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.yml", backend=Backend.NANO)


def test_load_config_default_path_honours_flowjet_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A real config placed at $FLOWJET_HOME is loaded, SOOTHE_HOME notwithstanding."""
    target = tmp_path / "flowjet"
    (target / "config").mkdir(parents=True)
    (target / "config" / "nano.yml").write_text(_NANO_YML, encoding="utf-8")
    monkeypatch.setenv("FLOWJET_HOME", str(target))
    monkeypatch.setenv("SOOTHE_HOME", str(tmp_path / "soothe"))

    config = load_config(backend=Backend.NANO)

    assert config.active_router_profile == "default"
