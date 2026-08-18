from __future__ import annotations

import time

import pytest
import yaml
from pydantic import ValidationError

from fund_agent_v2.audit import AuditSink, ToolRuntime
from fund_agent_v2.errors import ToolError, ToolErrorCode
from fund_agent_v2.schemas import (
    CalculateNavMetricsInput,
    FetchOfficialSourceInput,
    FundAgentPhase6Config,
    LoadFundProfileInput,
)
from fund_agent_v2.tools import DEFAULT_PHASE6_CONFIG, FundToolbox

EXPECTED_TOOLS = {
    "load_fund_profile",
    "calculate_nav_metrics",
    "compare_holdings",
    "retrieve_report_evidence",
    "fetch_official_source",
    "verify_citations",
    "compare_funds",
    "build_evidence_table",
    "validate_numeric_claims",
    "export_research_memo",
}


def test_phase6_config_is_closed_and_complete() -> None:
    raw = yaml.safe_load(DEFAULT_PHASE6_CONFIG.read_text(encoding="utf-8"))
    config = FundAgentPhase6Config.model_validate(raw)
    assert set(config.allowed_tools) == EXPECTED_TOOLS
    assert config.old_holdout_policy == "FROZEN_DO_NOT_READ"
    assert config.network_enabled is False
    assert config.llm_enabled is False
    assert config.arbitrary_shell_allowed is False
    assert config.arbitrary_filesystem_allowed is False
    assert config.secret_access_allowed is False
    assert set(config.file_sha256) == set(config.allowed_data_files)


def test_tool_input_schema_rejects_path_and_coercion() -> None:
    with pytest.raises(ValidationError):
        CalculateNavMetricsInput.model_validate(
            {"fund_codes": ["SYN001"], "path": "../../secret.env"}
        )
    with pytest.raises(ValidationError):
        CalculateNavMetricsInput.model_validate({"fund_codes": [2980]})


@pytest.mark.local_data
def test_profile_is_loaded_from_registered_dataset(toolbox: FundToolbox) -> None:
    result = toolbox.load_fund_profile(
        LoadFundProfileInput(profile="demo_synthetic"), request_id="profile-1"
    )
    assert result.fund_codes == ["SYN001", "SYN002", "SYN003"]
    assert result.periods == ["2025Q3", "2025Q4", "2026Q1", "2026Q2"]
    assert result.network_required is False
    assert result.contains_complete_pdf is False
    event = toolbox.audit_sink.events()[-1]
    assert event.status == "SUCCESS"
    assert event.tool_name == "load_fund_profile"


def test_unauthorized_fund_is_rejected_and_audited(toolbox: FundToolbox) -> None:
    tool_input = CalculateNavMetricsInput(fund_codes=["999999"])
    with pytest.raises(ToolError) as captured:
        toolbox.calculate_nav_metrics(tool_input, request_id="fund-denied")
    assert captured.value.code == ToolErrorCode.POLICY_VIOLATION
    event = toolbox.audit_sink.events()[-1]
    assert event.status == "ERROR"
    assert event.error_code == "POLICY_VIOLATION"
    assert event.retryable is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/report.pdf",
        "http://example.invalid/report.pdf",
        "https://example.invalid/not-registered.pdf",
        "https://user:password@example.invalid/report.pdf",
    ],
)
def test_official_source_requires_exact_local_allowlist(
    toolbox: FundToolbox, url: str
) -> None:
    with pytest.raises(ToolError) as captured:
        toolbox.fetch_official_source(
            FetchOfficialSourceInput(url=url), request_id="url-denied"
        )
    assert captured.value.code == ToolErrorCode.POLICY_VIOLATION


def test_runtime_classifies_timeout_and_redacts_payload() -> None:
    sink = AuditSink()
    runtime = ToolRuntime(
        allowed_tools={"slow_tool"},
        timeouts_seconds={"slow_tool": 0.005},
        audit_sink=sink,
    )
    tool_input = LoadFundProfileInput(profile="demo_synthetic")

    def slow_handler() -> LoadFundProfileInput:
        time.sleep(0.03)
        return tool_input

    with pytest.raises(ToolError) as captured:
        runtime.invoke(
            request_id="timeout-secret-marker",
            tool_name="slow_tool",
            tool_input=tool_input,
            handler=slow_handler,
        )
    assert captured.value.code == ToolErrorCode.TIMEOUT
    assert captured.value.retryable is True
    event = sink.events()[0]
    assert event.error_code == "TIMEOUT"
    assert "demo_synthetic" not in event.model_dump_json()
