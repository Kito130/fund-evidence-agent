from __future__ import annotations

from typing import cast

import pytest
from agents import FunctionTool

from fund_agent_v2.phase7_eval import evaluate_cases
from fund_agent_v2.phase7_io import load_eval_cases, load_phase7_config
from fund_agent_v2.sdk_adapter import (
    SDK_TOOLS,
    OnlineExecutionBlocked,
    assert_online_execution_authorized,
    build_sdk_agent,
    build_sdk_run_config,
)
from fund_agent_v2.single_agent import DeterministicMockSingleAgent
from fund_agent_v2.tools import FundToolbox


def test_sdk_contract_is_frozen_without_making_a_request() -> None:
    config = load_phase7_config()
    agent = build_sdk_agent(config)
    run_config = build_sdk_run_config(config)
    function_tools = [cast(FunctionTool, tool) for tool in SDK_TOOLS]
    assert agent.model == "gpt-5.6-terra"
    assert len(function_tools) == 10
    assert all(
        tool.params_json_schema.get("additionalProperties") is False
        for tool in function_tools
    )
    assert agent.model_settings.parallel_tool_calls is False
    assert agent.model_settings.store is False
    assert run_config.tracing_disabled is True
    assert run_config.trace_include_sensitive_data is False


def test_online_preflight_requires_explicit_authorization() -> None:
    with pytest.raises(OnlineExecutionBlocked, match="explicit"):
        assert_online_execution_authorized(explicit_authorization=False)


def test_online_preflight_requires_environment_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(OnlineExecutionBlocked, match="OPENAI_API_KEY"):
        assert_online_execution_authorized(explicit_authorization=True)


@pytest.mark.local_data
def test_new_v2_evaluation_suite_passes_offline(toolbox: FundToolbox) -> None:
    config = load_phase7_config()
    cases = load_eval_cases(config)
    agent = DeterministicMockSingleAgent(config=config, toolbox=toolbox)
    results, traces, summary = evaluate_cases(cases, agent=agent)
    assert len(cases) == 32
    assert all(result.passed for result in results)
    assert summary.pass_rate == 1.0
    assert summary.total_model_calls == 0
    assert summary.total_network_requests == 0
    assert summary.total_cost_usd == 0.0
    assert all("query" not in trace and "answer" not in trace for trace in traces)
