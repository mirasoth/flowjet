"""Unit tests for the nano bridge's custom-event mapping (``map_custom``)."""

from __future__ import annotations

from flowjet.core.bridges.nano.mapping import map_custom


def test_auto_gate_rejected_maps_to_descriptive_progress() -> None:
    progress = map_custom(
        {
            "type": "soothe.internal.tool.auto_gate.rejected",
            "tool": "run_command",
            "stage": "safety_check",
            "reason": "Command blocked by security rule: (?<!git\\s)rm\\s+-rf\\s+/",
            "rule_id": "command.dangerous.rm_root",
            "signature": "rm -rf /root/.cache/pip 2>/dev/null; df -h /",
        }
    )
    assert progress is not None
    assert progress.stage == "run_command"
    assert "run_command blocked by the approval gate" in progress.message
    assert "stage=safety_check" in progress.message
    assert "rule=command.dangerous.rm_root" in progress.message
    assert "Command blocked by security rule" in progress.message
    assert "[command: rm -rf /root/.cache/pip" in progress.message
    # The reason must be present — the whole point is a readable "why".
    assert "rm\\s+-rf" in progress.message


def test_auto_gate_rejected_without_optional_fields() -> None:
    progress = map_custom({"type": "soothe.internal.tool.auto_gate.rejected"})
    assert progress is not None
    assert progress.message == "tool blocked by the approval gate (stage=gate)"


def test_auto_gate_rejected_truncates_long_reason() -> None:
    progress = map_custom(
        {
            "type": "soothe.internal.tool.auto_gate.rejected",
            "tool": "run_command",
            "stage": "safety_check",
            "reason": "x" * 500,
            "signature": "c" * 300,
        }
    )
    assert progress is not None
    assert "x" * 200 in progress.message
    assert "x" * 201 not in progress.message
    assert "c" * 120 in progress.message
    assert "c" * 121 not in progress.message


def test_auto_gate_rejected_keeps_raw_for_rich_clients() -> None:
    raw = {
        "type": "soothe.internal.tool.auto_gate.rejected",
        "tool": "run_command",
        "stage": "deny_rule",
        "reason": "matched deny rule for run_command",
        "rule_id": "deny_rule",
    }
    progress = map_custom(raw)
    assert progress is not None
    assert progress.raw == raw


def test_generic_mapping_still_collapses_unknown_events() -> None:
    progress = map_custom({"type": "soothe.internal.other.thing"})
    assert progress is not None
    assert progress.message == "thing"
