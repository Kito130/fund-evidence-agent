from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    Tool,
    function_tool,
)
from openai.types.shared import Reasoning

from .errors import ToolError
from .phase7_schemas import FundAgentPhase7Config, OnlineAgentDraft
from .schemas import (
    BuildEvidenceTableInput,
    CalculateNavMetricsInput,
    CompareFundsInput,
    CompareHoldingsInput,
    ExportResearchMemoInput,
    FetchOfficialSourceInput,
    LoadFundProfileInput,
    RetrieveReportEvidenceInput,
    ValidateNumericClaimsInput,
    VerifyCitationsInput,
)
from .tools import WORKSPACE_ROOT, FundToolbox

DEFAULT_PROMPT_PATH = WORKSPACE_ROOT / "prompts/fund_agent_v1.md"


class OnlineExecutionBlocked(RuntimeError):
    pass


@dataclass
class FundSdkContext:
    toolbox: FundToolbox
    request_id: str
    export_approved: bool = False
    approved_by: str | None = None
    approval_id: str | None = None
    tool_events: list[dict[str, Any]] = field(default_factory=list)


def _result(value: Any) -> str:
    if hasattr(value, "model_dump_json"):
        return str(value.model_dump_json())
    return str(value)


def _error(exc: ToolError) -> str:
    return (
        '{"ok":false,"error_code":"'
        + exc.code.value
        + '","retryable":'
        + str(exc.retryable).lower()
        + "}"
    )


@function_tool(name_override="load_fund_profile", strict_mode=True)
def sdk_load_fund_profile(
    ctx: RunContextWrapper[FundSdkContext], tool_input: LoadFundProfileInput
) -> str:
    """Load the registered fund and report-period scope."""
    try:
        return _result(
            ctx.context.toolbox.load_fund_profile(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(name_override="calculate_nav_metrics", strict_mode=True)
def sdk_calculate_nav_metrics(
    ctx: RunContextWrapper[FundSdkContext], tool_input: CalculateNavMetricsInput
) -> str:
    """Recompute return, volatility, and drawdown on a common NAV window."""
    try:
        return _result(
            ctx.context.toolbox.calculate_nav_metrics(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(name_override="compare_holdings", strict_mode=True)
def sdk_compare_holdings(
    ctx: RunContextWrapper[FundSdkContext], tool_input: CompareHoldingsInput
) -> str:
    """Compare public top-ten holdings within one registered report period."""
    try:
        return _result(
            ctx.context.toolbox.compare_holdings(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(name_override="retrieve_report_evidence", strict_mode=True)
def sdk_retrieve_report_evidence(
    ctx: RunContextWrapper[FundSdkContext], tool_input: RetrieveReportEvidenceInput
) -> str:
    """Retrieve untrusted report excerpts within a fund and period allowlist."""
    try:
        return _result(
            ctx.context.toolbox.retrieve_report_evidence(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(name_override="fetch_official_source", strict_mode=True)
def sdk_fetch_official_source(
    ctx: RunContextWrapper[FundSdkContext], tool_input: FetchOfficialSourceInput
) -> str:
    """Locate an exact allowlisted official URL in the local manifest cache."""
    try:
        return _result(
            ctx.context.toolbox.fetch_official_source(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(name_override="verify_citations", strict_mode=True)
def sdk_verify_citations(
    ctx: RunContextWrapper[FundSdkContext], tool_input: VerifyCitationsInput
) -> str:
    """Verify exact URLs, document, page, chunk, and hashes for citations."""
    try:
        return _result(
            ctx.context.toolbox.verify_citations(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(name_override="compare_funds", strict_mode=True)
def sdk_compare_funds(
    ctx: RunContextWrapper[FundSdkContext], tool_input: CompareFundsInput
) -> str:
    """Run a bounded structured fund comparison."""
    try:
        return _result(
            ctx.context.toolbox.compare_funds(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(name_override="build_evidence_table", strict_mode=True)
def sdk_build_evidence_table(
    ctx: RunContextWrapper[FundSdkContext], tool_input: BuildEvidenceTableInput
) -> str:
    """Build claim-to-citation rows with exact excerpt location checks."""
    try:
        return _result(
            ctx.context.toolbox.build_evidence_table(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(name_override="validate_numeric_claims", strict_mode=True)
def sdk_validate_numeric_claims(
    ctx: RunContextWrapper[FundSdkContext], tool_input: ValidateNumericClaimsInput
) -> str:
    """Recompute and validate every numeric claim from registered data."""
    try:
        return _result(
            ctx.context.toolbox.validate_numeric_claims(
                tool_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


@function_tool(
    name_override="export_research_memo",
    strict_mode=True,
    needs_approval=True,
)
def sdk_export_research_memo(
    ctx: RunContextWrapper[FundSdkContext], tool_input: ExportResearchMemoInput
) -> str:
    """Export a verified memo only after an external human approval pause."""
    if (
        not ctx.context.export_approved
        or ctx.context.approved_by is None
        or ctx.context.approval_id is None
    ):
        return '{"ok":false,"error_code":"APPROVAL_REQUIRED","retryable":false}'
    approved_input = tool_input.model_copy(
        update={
            "human_approved": True,
            "approved_by": ctx.context.approved_by,
            "approval_id": ctx.context.approval_id,
        }
    )
    try:
        return _result(
            ctx.context.toolbox.export_research_memo(
                approved_input, request_id=ctx.context.request_id
            )
        )
    except ToolError as exc:
        return _error(exc)


SDK_TOOLS: list[Tool] = [
    sdk_load_fund_profile,
    sdk_calculate_nav_metrics,
    sdk_compare_holdings,
    sdk_retrieve_report_evidence,
    sdk_fetch_official_source,
    sdk_verify_citations,
    sdk_compare_funds,
    sdk_build_evidence_table,
    sdk_validate_numeric_claims,
    sdk_export_research_memo,
]


def build_sdk_agent(
    config: FundAgentPhase7Config,
    *,
    prompt_path: Path = DEFAULT_PROMPT_PATH,
) -> Agent[FundSdkContext]:
    instructions = prompt_path.read_text(encoding="utf-8")
    settings = ModelSettings(
        reasoning=Reasoning(effort=config.reasoning_effort),
        verbosity=config.text_verbosity,
        store=config.store,
        parallel_tool_calls=config.parallel_tool_calls,
        max_tokens=config.max_output_tokens,
    )
    return Agent[FundSdkContext](
        name="Evidence-constrained fund research agent",
        instructions=instructions,
        model=config.model,
        model_settings=settings,
        tools=SDK_TOOLS,
        output_type=OnlineAgentDraft,
    )


def build_sdk_run_config(config: FundAgentPhase7Config) -> RunConfig:
    return RunConfig(
        tracing_disabled=not config.sdk_tracing_enabled,
        trace_include_sensitive_data=config.sdk_trace_include_sensitive_data,
        workflow_name="fund-agent-v2-phase7",
    )


def assert_online_execution_authorized(*, explicit_authorization: bool) -> None:
    if not explicit_authorization:
        raise OnlineExecutionBlocked("explicit online API authorization is required")
    if not os.environ.get("OPENAI_API_KEY"):
        raise OnlineExecutionBlocked("OPENAI_API_KEY is not present")
