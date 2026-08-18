from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .schemas import (
    CitationRef,
    EvidenceTableRow,
    FundCode,
    NonEmptyStr,
    NumericClaimCheck,
    NumericClaimInput,
    PeriodId,
    StrictModel,
)


class FundAgentPhase7Config(StrictModel):
    schema_version: Literal[1]
    project_id: Literal["fund_agent"]
    phase: Literal["PHASE_7"]
    random_seed: int
    execution_mode: Literal["MOCK_ONLY"]
    online_api_status: Literal["BLOCKED_MISSING_EXPLICIT_AUTHORIZATION_AND_KEY"]
    old_holdout_policy: Literal["FROZEN_DO_NOT_READ"]
    new_holdout_status: Literal["NOT_CREATED"]
    agent_architecture: Literal["SINGLE_AGENT"]
    api_family: Literal["RESPONSES_API"]
    sdk: Literal["openai-agents"]
    sdk_version: Literal["0.19.3"]
    openai_version: Literal["2.53.0"]
    model: Literal["gpt-5.6-terra"]
    reasoning_effort: Literal["medium"]
    text_verbosity: Literal["medium"]
    store: Literal[False]
    parallel_tool_calls: Literal[False]
    sdk_tracing_enabled: Literal[False]
    sdk_trace_include_sensitive_data: Literal[False]
    local_redacted_trace_enabled: Literal[True]
    max_tool_steps: Annotated[int, Field(ge=1, le=20)]
    max_consecutive_tool_failures: Annotated[int, Field(ge=1, le=5)]
    max_input_chars: Annotated[int, Field(ge=100, le=10_000)]
    max_output_chars: Annotated[int, Field(ge=100, le=20_000)]
    max_output_tokens: Annotated[int, Field(ge=100, le=100_000)]
    minimum_evidence_score: Annotated[float, Field(ge=0.0, le=1.0)]
    max_cost_usd: Annotated[float, Field(gt=0.0, le=100.0)]
    request_timeout_seconds: Annotated[float, Field(gt=0.0, le=300.0)]
    export_enabled: Literal[False]
    allowed_fund_codes: list[FundCode]
    allowed_periods: list[PeriodId]
    evaluation_sets: dict[NonEmptyStr, NonEmptyStr]
    outputs: dict[NonEmptyStr, NonEmptyStr]


AgentStatus = Literal["ANSWERED", "REFUSED", "APPROVAL_REQUIRED", "ERROR"]


class ScopeDecision(StrictModel):
    allowed: bool
    intent: Literal["PROFILE", "NAV", "HOLDINGS", "EVIDENCE", "COMPARE", "NONE"]
    reason_codes: list[NonEmptyStr]
    fund_codes: list[FundCode]
    periods: list[PeriodId]


class AgentToolStep(StrictModel):
    step: Annotated[int, Field(ge=1)]
    tool_name: NonEmptyStr
    status: Literal["SUCCESS", "ERROR"]
    duration_ms: Annotated[float, Field(ge=0.0)]
    input_sha256: NonEmptyStr
    output_sha256: NonEmptyStr | None
    fund_codes: list[FundCode]
    periods: list[PeriodId]
    error_code: NonEmptyStr | None


class AgentUsage(StrictModel):
    provider: Literal["DETERMINISTIC_MOCK", "OPENAI_AGENTS_SDK"]
    model: NonEmptyStr
    model_calls: Annotated[int, Field(ge=0)]
    network_requests: Annotated[int, Field(ge=0)]
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    estimated_cost_usd: Annotated[float, Field(ge=0.0)]
    elapsed_ms: Annotated[float, Field(ge=0.0)]


class AgentResponse(StrictModel):
    request_id: NonEmptyStr
    status: AgentStatus
    answer: str
    reason_codes: list[NonEmptyStr]
    citations: list[CitationRef]
    numeric_checks: list[NumericClaimCheck]
    evidence_rows: list[EvidenceTableRow]
    tool_steps: list[AgentToolStep]
    usage: AgentUsage


class OnlineAgentDraft(StrictModel):
    status: Literal["ANSWERED", "REFUSED", "APPROVAL_REQUIRED"]
    answer: Annotated[str, Field(max_length=4000)]
    reason_codes: list[NonEmptyStr]
    citations: list[CitationRef]
    numeric_claims: list[NumericClaimInput]


EvalSuite = Literal[
    "development",
    "adversarial",
    "tool_selection",
    "numeric_consistency",
    "citation_integrity",
    "refusal",
    "prompt_injection",
]


class EvalCase(StrictModel):
    case_id: NonEmptyStr
    suite: EvalSuite
    query: Annotated[str, Field(min_length=1, max_length=1000)]
    expected_status: AgentStatus
    expected_tools: list[NonEmptyStr]
    expected_reason_codes: list[NonEmptyStr]
    expected_fund_codes: list[FundCode]
    expected_periods: list[PeriodId]
    require_numeric_validation: bool
    require_citation_validation: bool


class EvalCaseResult(StrictModel):
    case_id: NonEmptyStr
    suite: EvalSuite
    passed: bool
    status_correct: bool
    tool_route_correct: bool
    scope_arguments_correct: bool
    reason_correct: bool
    numeric_valid: bool
    citations_valid: bool
    budget_respected: bool
    latency_ms: float
    tool_steps: int
    cost_usd: float
    failure_reasons: list[NonEmptyStr]


class EvalSummary(StrictModel):
    phase: Literal["PHASE_7_OFFLINE"]
    execution_mode: Literal["MOCK_ONLY"]
    total_cases: int
    passed_cases: int
    pass_rate: float
    suite_metrics: dict[str, dict[str, float | int]]
    average_tool_steps: float
    average_latency_ms: float
    total_model_calls: Literal[0]
    total_network_requests: Literal[0]
    total_cost_usd: Annotated[float, Field(ge=0.0, le=0.0)]
    old_holdout_read_count: Literal[0]
    new_holdout_open_count: Literal[0]
    online_evaluation_status: Literal["NOT_RUN_REQUIRES_EXPLICIT_AUTHORIZATION"]
