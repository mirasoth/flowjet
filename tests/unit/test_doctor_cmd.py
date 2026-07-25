"""Unit tests for ``fj doctor``."""

from __future__ import annotations

from types import SimpleNamespace

from fj_ai.cli import parse_args
from fj_ai.doctor_cmd import parse_doctor_args, run_doctor


def test_parse_args_doctor_command() -> None:
    args = parse_args(["doctor", "--deep", "--live-llm"])
    assert args.command == "doctor"
    assert args.doctor_argv == ["--deep", "--live-llm"]


def test_parse_doctor_args_defaults() -> None:
    args = parse_doctor_args([])
    assert args.deep is False
    assert args.live_llm is False
    assert args.output_format == "text"
    assert args.fail_on == "error"


def test_main_doctor_dispatches(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from fj_ai import cli

    called: list[list[str]] = []

    monkeypatch.setattr(cli, "configure_cli_logging", lambda **_k: None)
    monkeypatch.setattr(
        "fj_ai.doctor_cmd.run_doctor",
        lambda argv: called.append(list(argv)) or 0,
    )

    def boom(*_a: object, **_k: object) -> int:
        raise AssertionError("doctor must not use asyncio.run in main")

    monkeypatch.setattr(cli.asyncio, "run", boom)
    assert cli.main(["doctor", "--deep"]) == 0
    assert called == [["--deep"]]


def test_run_doctor_json(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    async def fake_diagnose(_config=None, **kwargs):
        assert kwargs.get("deep") is False
        return [
            {
                "category": "tool_deps",
                "status": "ok",
                "checks": [{"name": "rg", "status": "ok", "message": "rg ok", "details": {}}],
                "message": None,
            }
        ]

    monkeypatch.setattr("fj_ai.doctor_cmd._run_diagnose", fake_diagnose)
    monkeypatch.setattr(
        "fj_ai.agent.load_config",
        lambda _path=None: SimpleNamespace(),
    )
    assert run_doctor(["--format", "json", "--no-color"]) == 0
    out = capsys.readouterr().out
    assert '"overall_status": "ok"' in out
    assert "tool_deps" in out


def test_run_doctor_progressive_text(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    async def fake_diagnose(_config=None, **_kwargs):
        return [
            {
                "category": "providers",
                "status": "warning",
                "checks": [
                    {
                        "name": "openai",
                        "status": "warning",
                        "message": "api key missing",
                        "details": {"remediation": "set OPENAI_API_KEY"},
                    }
                ],
                "message": None,
            }
        ]

    monkeypatch.setattr("fj_ai.doctor_cmd._run_diagnose", fake_diagnose)
    monkeypatch.setattr(
        "fj_ai.agent.load_config",
        lambda _path=None: SimpleNamespace(),
    )
    code = run_doctor(["--no-color", "--fail-on", "warning"])
    assert code == 1
    out = capsys.readouterr().out
    assert "progressive diagnosis" in out
    assert "Providers" in out
    assert "api key missing" in out
    assert "Remediation: set OPENAI_API_KEY" in out


def test_run_doctor_missing_diagnose_api(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    async def boom(_config=None, **_kwargs):
        raise RuntimeError("soothe-nano diagnose API unavailable")

    monkeypatch.setattr("fj_ai.doctor_cmd._run_diagnose", boom)
    monkeypatch.setattr(
        "fj_ai.agent.load_config",
        lambda _path=None: SimpleNamespace(),
    )
    assert run_doctor(["--no-color"]) == 1
    assert "diagnose API unavailable" in capsys.readouterr().err
