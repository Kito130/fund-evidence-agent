from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
FundCode = Annotated[
    str,
    StringConstraints(pattern=r"^(?:[0-9]{6}|SYN[0-9]{3})$"),
]
PeriodId = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}Q[1-4]$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SafeFileName = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.md$"),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FundAgentPhase6Config(StrictModel):
    schema_version: Literal[1]
    project_id: Literal["fund_agent"]
    phase: Literal["PHASE_6"]
    random_seed: int
    dataset_profile: Literal["demo_synthetic"]
    dataset_root: NonEmptyStr
    old_holdout_policy: Literal["FROZEN_DO_NOT_READ"]
    llm_enabled: Literal[False]
    network_enabled: Literal[False]
    paid_api_enabled: Literal[False]
    arbitrary_shell_allowed: Literal[False]
    arbitrary_filesystem_allowed: Literal[False]
    secret_access_allowed: Literal[False]
    allowed_tools: list[NonEmptyStr]
    allowed_fund_codes: list[FundCode]
    allowed_periods: list[PeriodId]
    allowed_official_domains: list[NonEmptyStr]
    allowed_data_files: list[NonEmptyStr]
    file_sha256: dict[NonEmptyStr, Sha256]
    tool_timeouts_seconds: dict[NonEmptyStr, float]
    maximum_top_k: Annotated[int, Field(ge=1, le=100)]
    maximum_claims_per_call: Annotated[int, Field(ge=1, le=100)]
    export_root: NonEmptyStr
    audit_retention: Literal["redacted_metadata_only"]
    outputs: dict[NonEmptyStr, NonEmptyStr]


class LoadFundProfileInput(StrictModel):
    profile: Literal["demo_synthetic"]


class FundProfileOutput(StrictModel):
    profile: Literal["demo_synthetic"]
    dataset_version: NonEmptyStr
    fund_codes: list[FundCode]
    periods: list[PeriodId]
    counts: dict[str, int]
    contains_real_fund_data: bool
    contains_complete_pdf: bool
    network_required: Literal[False]
    source_policy: NonEmptyStr


class CalculateNavMetricsInput(StrictModel):
    fund_codes: Annotated[list[FundCode], Field(min_length=1, max_length=3)]
    start_date: date | None = None
    end_date: date | None = None
    nav_field: Literal["cumulative_nav"] = "cumulative_nav"
    annualization_factor: Literal[252] = 252


class NavMetric(StrictModel):
    fund_code: FundCode
    fund_name: NonEmptyStr
    start_date: date
    end_date: date
    nav_observations: int
    return_observations: int
    cumulative_change: float
    annualized_volatility: float
    max_drawdown: float
    drawdown_peak_date: date
    drawdown_trough_date: date
    drawdown_recovery_date: date | None


class NavMetricsOutput(StrictModel):
    common_start_date: date
    common_end_date: date
    common_observations: int
    nav_field: Literal["cumulative_nav"]
    annualization_factor: Literal[252]
    metrics: list[NavMetric]


class CompareHoldingsInput(StrictModel):
    fund_code_a: FundCode
    fund_code_b: FundCode
    period: PeriodId


class HoldingMetric(StrictModel):
    fund_code: FundCode
    fund_name: NonEmptyStr
    c10: float
    hhi10: float
    disclosed_holding_count: Literal[10]


class HoldingsComparisonOutput(StrictModel):
    period: PeriodId
    fund_a: HoldingMetric
    fund_b: HoldingMetric
    common_stock_count: int
    common_stock_codes: list[NonEmptyStr]
    name_jaccard: float
    common_nav_share: float
    terminology: Literal["公开前十大持仓重合"]


class RetrieveReportEvidenceInput(StrictModel):
    query: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)
    ]
    fund_codes: Annotated[list[FundCode], Field(min_length=1, max_length=3)]
    periods: Annotated[list[PeriodId], Field(min_length=1, max_length=2)]
    top_k: Annotated[int, Field(ge=1, le=10)] = 3


class CitationRef(StrictModel):
    doc_id: NonEmptyStr
    fund_code: FundCode
    fund_name: NonEmptyStr
    period: PeriodId
    period_end: date
    physical_page: Annotated[int, Field(ge=1)]
    chunk_id: NonEmptyStr
    text_hash: Sha256
    page_text_hash: Sha256
    source_pdf_sha256: Sha256
    announcement_url: NonEmptyStr
    file_url: str


class EvidenceCard(StrictModel):
    rank: Annotated[int, Field(ge=1)]
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    query_hash: Sha256
    evidence_text: NonEmptyStr
    untrusted_content: Literal[True]
    injection_signals: list[NonEmptyStr]
    citation: CitationRef


class RetrievalOutput(StrictModel):
    model_version: Literal["f5_char_ngram_tfidf_v1"]
    query_hash: Sha256
    result_count: int
    cards: list[EvidenceCard]


class FetchOfficialSourceInput(StrictModel):
    url: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=500)
    ]


class OfficialSourceOutput(StrictModel):
    url: NonEmptyStr
    domain: NonEmptyStr
    source_kind: Literal["announcement", "report_file"]
    doc_id: NonEmptyStr
    fund_code: FundCode
    period: PeriodId
    source_pdf_sha256: Sha256
    cache_mode: Literal["LOCAL_MANIFEST_ONLY"]
    network_request_count: Literal[0]
    untrusted_content: Literal[True]


class VerifyCitationsInput(StrictModel):
    citations: Annotated[list[CitationRef], Field(min_length=1, max_length=20)]


class CitationCheck(StrictModel):
    chunk_id: NonEmptyStr
    valid: bool
    checks: dict[str, bool]
    reason_codes: list[NonEmptyStr]


class CitationVerificationOutput(StrictModel):
    all_valid: bool
    checks: list[CitationCheck]


class CompareFundsInput(StrictModel):
    fund_code_a: FundCode
    fund_code_b: FundCode
    period: PeriodId
    start_date: date | None = None
    end_date: date | None = None


class FundComparisonOutput(StrictModel):
    fund_code_a: FundCode
    fund_code_b: FundCode
    period: PeriodId
    common_start_date: date
    common_end_date: date
    nav_metrics: list[NavMetric]
    cumulative_change_difference_a_minus_b: float
    volatility_difference_a_minus_b: float
    holdings: HoldingsComparisonOutput


class EvidenceClaimInput(StrictModel):
    claim_id: NonEmptyStr
    claim_text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]
    evidence_excerpt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    citation: CitationRef


class BuildEvidenceTableInput(StrictModel):
    claims: Annotated[list[EvidenceClaimInput], Field(min_length=1, max_length=20)]


class EvidenceTableRow(StrictModel):
    claim_id: NonEmptyStr
    claim_text: NonEmptyStr
    evidence_excerpt: NonEmptyStr
    chunk_id: NonEmptyStr
    physical_page: int
    citation_valid: bool
    exact_excerpt: bool
    status: Literal["LOCATED", "REJECTED"]
    limitation: Literal["location_and_exact_excerpt_only_not_semantic_entailment"]


class EvidenceTableOutput(StrictModel):
    all_located: bool
    rows: list[EvidenceTableRow]


NumericMetricName = Literal[
    "cumulative_change",
    "annualized_volatility",
    "max_drawdown",
    "c10",
    "hhi10",
    "name_jaccard",
    "common_nav_share",
    "pearson_correlation",
]


class NumericClaimInput(StrictModel):
    claim_id: NonEmptyStr
    metric: NumericMetricName
    claimed_value: float
    fund_code: FundCode
    comparison_fund_code: FundCode | None = None
    period: PeriodId | None = None
    start_date: date | None = None
    end_date: date | None = None
    absolute_tolerance: Annotated[float, Field(ge=0.0, le=0.01)] = 1.0e-9


class ValidateNumericClaimsInput(StrictModel):
    claims: Annotated[list[NumericClaimInput], Field(min_length=1, max_length=20)]


class NumericClaimCheck(StrictModel):
    claim_id: NonEmptyStr
    metric: NumericMetricName
    claimed_value: float
    expected_value: float | None
    absolute_difference: float | None
    valid: bool
    reason_code: NonEmptyStr


class NumericValidationOutput(StrictModel):
    all_valid: bool
    checks: list[NumericClaimCheck]


class ExportResearchMemoInput(StrictModel):
    file_name: SafeFileName
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
    ]
    markdown_body: Annotated[str, StringConstraints(min_length=1, max_length=100_000)]
    evidence_claims: Annotated[
        list[EvidenceClaimInput], Field(min_length=1, max_length=20)
    ]
    numeric_claims: Annotated[
        list[NumericClaimInput], Field(min_length=1, max_length=20)
    ]
    human_approved: bool
    approved_by: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)
    ]
    approval_id: Annotated[
        str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{5,79}$")
    ]


class ExportResearchMemoOutput(StrictModel):
    status: Literal["EXPORTED"]
    relative_path: NonEmptyStr
    content_sha256: Sha256
    evidence_table_sha256: Sha256
    numeric_validation_sha256: Sha256
    approval_id: NonEmptyStr
    bytes_written: Annotated[int, Field(gt=0)]


class AuditEvent(StrictModel):
    event_id: NonEmptyStr
    request_id: NonEmptyStr
    tool_name: NonEmptyStr
    started_at: datetime
    finished_at: datetime
    duration_ms: Annotated[float, Field(ge=0.0)]
    status: Literal["SUCCESS", "ERROR"]
    input_sha256: Sha256
    output_sha256: Sha256 | None
    error_code: NonEmptyStr | None
    retryable: bool
