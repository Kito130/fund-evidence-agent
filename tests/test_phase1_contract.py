from pathlib import Path

import yaml

from fund_agent_v2 import FundAgentPhase1Config

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_phase1_config_is_closed() -> None:
    raw = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "v2_agent.yaml").read_text(encoding="utf-8")
    )
    config = FundAgentPhase1Config.model_validate(raw)

    assert config.llm_enabled is False
    assert config.network_enabled is False
    assert config.paid_api_enabled is False
    assert config.export_enabled is False
    assert config.old_holdout_policy == "FROZEN_DO_NOT_READ"
    assert config.tool_policy.arbitrary_shell_allowed is False
    assert config.tool_policy.arbitrary_filesystem_allowed is False
