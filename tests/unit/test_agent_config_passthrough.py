"""Config passthrough — deployment agent config reaches the soothe host config.

Verifies the split-file loading chain (nano.yml + sibling soothe.yml →
``HostSootheConfig``) carries:

- ``agent.name`` / ``agent.rules`` (nano-owned keys from nano.yml);
- ``agent.assistant_identity`` (host-owned key from soothe.yml);
- ``<HOST_RULES>`` rendering in ``resolve_system_prompt`` (soothe-nano feature).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowjet.core.agent.config import FlowJetConfigLoader
from flowjet.core.backend_config import Backend

pytest.importorskip("soothe")


def test_split_config_carries_rules_and_identity(tmp_path: Path) -> None:
    nano_yml = tmp_path / "nano.yml"
    nano_yml.write_text(
        "agent:\n"
        "  name: MiraCloud Agent\n"
        "  rules:\n"
        "    - Write valuable final outputs to deliverables/.\n"
        "    - Never put temporary files in deliverables/.\n",
        encoding="utf-8",
    )
    soothe_yml = tmp_path / "soothe.yml"
    soothe_yml.write_text(
        "agent:\n"
        "  assistant_identity:\n"
        "    creator: MiraCloud\n"
        "    role_description: an autonomous research agent on MiraCloud Agentspace\n"
        "    vendor_denylist:\n"
        "      - FlowJet\n"
        "      - Soothe\n"
        "      - soothe-nano\n",
        encoding="utf-8",
    )

    config = FlowJetConfigLoader.load(nano_yml, backend=Backend.SOOTHE)

    # nano-owned keys from nano.yml survive the split merge.
    assert config.agent.name == "MiraCloud Agent"
    assert config.agent.rules == [
        "Write valuable final outputs to deliverables/.",
        "Never put temporary files in deliverables/.",
    ]

    # host-owned key from soothe.yml survives too.
    assert config.agent.assistant_identity.creator == "MiraCloud"
    assert "FlowJet" in config.agent.assistant_identity.vendor_denylist

    # The host persona renders the configured byline.
    from soothe.identity.persona import build_assistant_identity_block

    block = build_assistant_identity_block(
        "MiraCloud Agent", identity=config.agent.assistant_identity
    )
    assert (
        "You are MiraCloud Agent, an autonomous research agent on MiraCloud Agentspace invented by MiraCloud."
        in block
    )

    # agent.rules reaches the system prompt as a <HOST_RULES> block.
    prompt = config.resolve_system_prompt()
    assert "<HOST_RULES>" in prompt
    assert "- Write valuable final outputs to deliverables/." in prompt
    assert "- Never put temporary files in deliverables/." in prompt


def test_split_config_without_rules_has_no_host_rules_block(tmp_path: Path) -> None:
    nano_yml = tmp_path / "nano.yml"
    nano_yml.write_text("agent:\n  name: TestAgent\n", encoding="utf-8")

    config = FlowJetConfigLoader.load(nano_yml, backend=Backend.SOOTHE)

    assert config.agent.rules is None
    assert "<HOST_RULES>" not in config.resolve_system_prompt()
