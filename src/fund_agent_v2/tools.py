from __future__ import annotations

import hashlib
import math
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from .audit import AuditSink, ToolRuntime
from .calculations import (
    annualized_volatility,
    c10,
    common_nav_share,
    cumulative_change,
    hhi10,
    maximum_drawdown,
    name_jaccard,
    pearson_correlation,
    simple_returns,
)
from .errors import ToolError, ToolErrorCode
from .policy import ToolPolicy
from .repository import DatasetRepository, load_phase6_config
from .retrieval_engine import (
    MODEL_VERSION,
    detect_injection_signals,
    retrieve,
    sha256_text,
)
from .schemas import (
    BuildEvidenceTableInput,
    CalculateNavMetricsInput,
    CitationCheck,
    CitationRef,
    CitationVerificationOutput,
    CompareFundsInput,
    CompareHoldingsInput,
    EvidenceCard,
    EvidenceTableOutput,
    EvidenceTableRow,
    ExportResearchMemoInput,
    ExportResearchMemoOutput,
    FetchOfficialSourceInput,
    FundComparisonOutput,
    FundProfileOutput,
    HoldingMetric,
    HoldingsComparisonOutput,
    LoadFundProfileInput,
    NavMetric,
    NavMetricsOutput,
    NumericClaimCheck,
    NumericClaimInput,
    NumericValidationOutput,
    OfficialSourceOutput,
    RetrievalOutput,
    RetrieveReportEvidenceInput,
    ValidateNumericClaimsInput,
    VerifyCitationsInput,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PHASE6_CONFIG = WORKSPACE_ROOT / "configs/phase6_tools.yaml"


def _date(value: object) -> date:
    return date.fromisoformat(str(value))


def _float(value: object) -> float:
    result = float(str(value))
    if not math.isfinite(result):
        raise ToolError(ToolErrorCode.DATA_INTEGRITY, "non-finite numeric value")
    return result


class FundToolbox:
    def __init__(
        self,
        *,
        policy: ToolPolicy,
        repository: DatasetRepository,
        runtime: ToolRuntime,
        audit_sink: AuditSink,
    ) -> None:
        self.policy = policy
        self.repository = repository
        self.runtime = runtime
        self.audit_sink = audit_sink

    def load_fund_profile(
        self, tool_input: LoadFundProfileInput, *, request_id: str
    ) -> FundProfileOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="load_fund_profile",
            tool_input=tool_input,
            handler=self._load_fund_profile,
        )

    def _load_fund_profile(self) -> FundProfileOutput:
        profile = self.repository.json_object("profile.json")
        holdings = self.repository.csv_rows("top10_holdings.csv")
        fund_codes = sorted({row["fund_code"] for row in holdings})
        periods = sorted({row["period"] for row in holdings})
        self.policy.require_funds(fund_codes)
        self.policy.require_periods(periods)
        counts_raw = profile.get("counts")
        if not isinstance(counts_raw, dict):
            raise ToolError(ToolErrorCode.DATA_INTEGRITY, "profile counts are missing")
        counts = {str(key): int(value) for key, value in counts_raw.items()}
        return FundProfileOutput(
            profile=self.policy.config.dataset_profile,
            dataset_version=str(profile["dataset_version"]),
            fund_codes=fund_codes,
            periods=periods,
            counts=counts,
            contains_real_fund_data=bool(profile["contains_real_fund_data"]),
            contains_complete_pdf=bool(profile["contains_complete_pdf"]),
            network_required=False,
            source_policy=str(profile["source_policy"]),
        )

    def calculate_nav_metrics(
        self, tool_input: CalculateNavMetricsInput, *, request_id: str
    ) -> NavMetricsOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="calculate_nav_metrics",
            tool_input=tool_input,
            handler=lambda: self._calculate_nav_metrics(tool_input),
        )

    def _nav_series(
        self,
        fund_codes: list[str],
        start_date: date | None,
        end_date: date | None,
    ) -> dict[str, list[tuple[date, float, str]]]:
        self.policy.require_funds(fund_codes)
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "start_date exceeds end_date")
        series: dict[str, list[tuple[date, float, str]]] = {
            code: [] for code in fund_codes
        }
        for row in self.repository.csv_rows("nav_daily.csv"):
            code = row["fund_code"]
            if code not in series:
                continue
            observation_date = _date(row["date"])
            if start_date is not None and observation_date < start_date:
                continue
            if end_date is not None and observation_date > end_date:
                continue
            series[code].append(
                (observation_date, _float(row["cumulative_nav"]), row["fund_name"])
            )
        if any(not values for values in series.values()):
            raise ToolError(ToolErrorCode.NOT_FOUND, "NAV observations are missing")
        common_dates = set.intersection(
            *({observation[0] for observation in values} for values in series.values())
        )
        if len(common_dates) < 3:
            raise ToolError(
                ToolErrorCode.INVALID_INPUT,
                "common NAV window needs at least three observations",
            )
        return {
            code: sorted(
                (item for item in values if item[0] in common_dates),
                key=lambda item: item[0],
            )
            for code, values in series.items()
        }

    def _calculate_nav_metrics(
        self, tool_input: CalculateNavMetricsInput
    ) -> NavMetricsOutput:
        series = self._nav_series(
            tool_input.fund_codes, tool_input.start_date, tool_input.end_date
        )
        metrics: list[NavMetric] = []
        for code in tool_input.fund_codes:
            observations = series[code]
            dates = [item[0] for item in observations]
            values = [item[1] for item in observations]
            returns = simple_returns(values)
            drawdown = maximum_drawdown(dates, values)
            metrics.append(
                NavMetric(
                    fund_code=code,
                    fund_name=observations[0][2],
                    start_date=dates[0],
                    end_date=dates[-1],
                    nav_observations=len(values),
                    return_observations=len(returns),
                    cumulative_change=cumulative_change(values),
                    annualized_volatility=annualized_volatility(returns),
                    max_drawdown=float(drawdown["max_drawdown"]),
                    drawdown_peak_date=drawdown["peak_date"],
                    drawdown_trough_date=drawdown["trough_date"],
                    drawdown_recovery_date=drawdown["recovery_date"],
                )
            )
        first = next(iter(series.values()))
        return NavMetricsOutput(
            common_start_date=first[0][0],
            common_end_date=first[-1][0],
            common_observations=len(first),
            nav_field="cumulative_nav",
            annualization_factor=252,
            metrics=metrics,
        )

    def compare_holdings(
        self, tool_input: CompareHoldingsInput, *, request_id: str
    ) -> HoldingsComparisonOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="compare_holdings",
            tool_input=tool_input,
            handler=lambda: self._compare_holdings(tool_input),
        )

    def _holding_rows(self, fund_code: str, period: str) -> list[dict[str, str]]:
        rows = [
            row
            for row in self.repository.csv_rows("top10_holdings.csv")
            if row["fund_code"] == fund_code and row["period"] == period
        ]
        rows.sort(key=lambda row: int(row["public_holding_rank"]))
        if len(rows) != 10:
            raise ToolError(
                ToolErrorCode.DATA_INTEGRITY,
                f"{fund_code}/{period} does not have exactly ten holdings",
            )
        return rows

    def _compare_holdings(
        self, tool_input: CompareHoldingsInput
    ) -> HoldingsComparisonOutput:
        if tool_input.fund_code_a == tool_input.fund_code_b:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "funds must be distinct")
        self.policy.require_funds([tool_input.fund_code_a, tool_input.fund_code_b])
        self.policy.require_periods([tool_input.period])
        rows_a = self._holding_rows(tool_input.fund_code_a, tool_input.period)
        rows_b = self._holding_rows(tool_input.fund_code_b, tool_input.period)
        weights_a = [Decimal(row["nav_ratio_pct"]) / Decimal(100) for row in rows_a]
        weights_b = [Decimal(row["nav_ratio_pct"]) / Decimal(100) for row in rows_b]
        by_code_a = {
            row["stock_code"]: Decimal(row["nav_ratio_pct"]) / Decimal(100)
            for row in rows_a
        }
        by_code_b = {
            row["stock_code"]: Decimal(row["nav_ratio_pct"]) / Decimal(100)
            for row in rows_b
        }
        common_codes = sorted(set(by_code_a) & set(by_code_b))
        return HoldingsComparisonOutput(
            period=tool_input.period,
            fund_a=HoldingMetric(
                fund_code=tool_input.fund_code_a,
                fund_name=rows_a[0]["fund_name"],
                c10=float(c10(weights_a)),
                hhi10=float(hhi10(weights_a)),
                disclosed_holding_count=10,
            ),
            fund_b=HoldingMetric(
                fund_code=tool_input.fund_code_b,
                fund_name=rows_b[0]["fund_name"],
                c10=float(c10(weights_b)),
                hhi10=float(hhi10(weights_b)),
                disclosed_holding_count=10,
            ),
            common_stock_count=len(common_codes),
            common_stock_codes=common_codes,
            name_jaccard=float(
                name_jaccard(
                    (row["stock_name"] for row in rows_a),
                    (row["stock_name"] for row in rows_b),
                )
            ),
            common_nav_share=float(common_nav_share(by_code_a, by_code_b)),
            terminology="公开前十大持仓重合",
        )

    def retrieve_report_evidence(
        self, tool_input: RetrieveReportEvidenceInput, *, request_id: str
    ) -> RetrievalOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="retrieve_report_evidence",
            tool_input=tool_input,
            handler=lambda: self._retrieve_report_evidence(tool_input),
        )

    @staticmethod
    def _citation_from_chunk(chunk: dict[str, Any]) -> CitationRef:
        return CitationRef(
            doc_id=str(chunk["doc_id"]),
            fund_code=str(chunk["fund_code"]),
            fund_name=str(chunk["fund_name"]),
            period=str(chunk["period"]),
            period_end=_date(chunk["period_end"]),
            physical_page=int(chunk["page_number"]),
            chunk_id=str(chunk["chunk_id"]),
            text_hash=str(chunk["text_hash"]),
            page_text_hash=str(chunk["page_text_hash"]),
            source_pdf_sha256=str(chunk["source_pdf_sha256"]),
            announcement_url=str(chunk["announcement_url"]),
            file_url=str(chunk["file_url"]),
        )

    def _retrieve_report_evidence(
        self, tool_input: RetrieveReportEvidenceInput
    ) -> RetrievalOutput:
        self.policy.require_funds(tool_input.fund_codes)
        self.policy.require_periods(tool_input.periods)
        if tool_input.top_k > self.policy.config.maximum_top_k:
            raise ToolError(ToolErrorCode.POLICY_VIOLATION, "top_k exceeds policy")
        chunks = self.repository.jsonl_objects("chunks.jsonl")
        index = self.repository.json_object("tfidf_index.json")
        scored = retrieve(
            tool_input.query,
            index=index,
            chunks=chunks,
            fund_codes=set(tool_input.fund_codes),
            periods=set(tool_input.periods),
            top_k=tool_input.top_k,
        )
        query_hash = sha256_text(tool_input.query)
        cards = [
            EvidenceCard(
                rank=rank,
                score=score,
                query_hash=query_hash,
                evidence_text=str(chunk["text"]),
                untrusted_content=True,
                injection_signals=detect_injection_signals(str(chunk["text"])),
                citation=self._citation_from_chunk(chunk),
            )
            for rank, (score, chunk) in enumerate(scored, start=1)
        ]
        return RetrievalOutput(
            model_version=MODEL_VERSION,
            query_hash=query_hash,
            result_count=len(cards),
            cards=cards,
        )

    def fetch_official_source(
        self, tool_input: FetchOfficialSourceInput, *, request_id: str
    ) -> OfficialSourceOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="fetch_official_source",
            tool_input=tool_input,
            handler=lambda: self._fetch_official_source(tool_input),
        )

    def _fetch_official_source(
        self, tool_input: FetchOfficialSourceInput
    ) -> OfficialSourceOutput:
        domain = self.policy.require_official_url(tool_input.url)
        for row in self.repository.csv_rows("source_manifest.csv"):
            if tool_input.url == row["announcement_url"]:
                source_kind: Literal["announcement", "report_file"] = "announcement"
            elif tool_input.url == row["file_url"]:
                source_kind = "report_file"
            else:
                continue
            self.policy.require_funds([row["fund_code"]])
            self.policy.require_periods([row["period"]])
            return OfficialSourceOutput(
                url=tool_input.url,
                domain=domain,
                source_kind=source_kind,
                doc_id=row["doc_id"],
                fund_code=row["fund_code"],
                period=row["period"],
                source_pdf_sha256=row["sha256"],
                cache_mode="LOCAL_MANIFEST_ONLY",
                network_request_count=0,
                untrusted_content=True,
            )
        raise ToolError(
            ToolErrorCode.POLICY_VIOLATION,
            "URL is not registered in the local official-source manifest",
        )

    def verify_citations(
        self, tool_input: VerifyCitationsInput, *, request_id: str
    ) -> CitationVerificationOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="verify_citations",
            tool_input=tool_input,
            handler=lambda: self._verify_citations(tool_input),
        )

    def _citation_check(self, citation: CitationRef) -> CitationCheck:
        self.policy.require_funds([citation.fund_code])
        self.policy.require_periods([citation.period])
        chunks = self.repository.jsonl_objects("chunks.jsonl")
        chunk = next(
            (row for row in chunks if str(row.get("chunk_id")) == citation.chunk_id),
            None,
        )
        if chunk is None:
            return CitationCheck(
                chunk_id=citation.chunk_id,
                valid=False,
                checks={"chunk_registered": False},
                reason_codes=["chunk_not_registered"],
            )
        manifest_rows = self.repository.csv_rows("source_manifest.csv")
        manifest = next(
            (row for row in manifest_rows if row["doc_id"] == citation.doc_id), None
        )
        checks = {
            "chunk_registered": True,
            "doc_id": str(chunk["doc_id"]) == citation.doc_id,
            "fund_code": str(chunk["fund_code"]) == citation.fund_code,
            "fund_name": str(chunk["fund_name"]) == citation.fund_name,
            "period": str(chunk["period"]) == citation.period,
            "period_end": _date(chunk["period_end"]) == citation.period_end,
            "physical_page": int(chunk["page_number"]) == citation.physical_page,
            "text_hash": str(chunk["text_hash"]) == citation.text_hash
            and sha256_text(str(chunk["text"])) == citation.text_hash,
            "page_text_hash": str(chunk["page_text_hash"]) == citation.page_text_hash,
            "source_pdf_sha256": str(chunk["source_pdf_sha256"])
            == citation.source_pdf_sha256,
            "announcement_url": str(chunk["announcement_url"])
            == citation.announcement_url,
            "file_url": str(chunk["file_url"]) == citation.file_url,
            "manifest": manifest is not None
            and manifest["fund_code"] == citation.fund_code
            and manifest["period"] == citation.period
            and manifest["announcement_url"] == citation.announcement_url
            and manifest["file_url"] == citation.file_url
            and manifest["sha256"] == citation.source_pdf_sha256,
        }
        reasons = [name for name, passed in checks.items() if not passed]
        return CitationCheck(
            chunk_id=citation.chunk_id,
            valid=not reasons,
            checks=checks,
            reason_codes=reasons or ["verified"],
        )

    def _verify_citations(
        self, tool_input: VerifyCitationsInput
    ) -> CitationVerificationOutput:
        checks = [self._citation_check(citation) for citation in tool_input.citations]
        return CitationVerificationOutput(
            all_valid=all(check.valid for check in checks), checks=checks
        )

    def compare_funds(
        self, tool_input: CompareFundsInput, *, request_id: str
    ) -> FundComparisonOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="compare_funds",
            tool_input=tool_input,
            handler=lambda: self._compare_funds(tool_input),
        )

    def _compare_funds(self, tool_input: CompareFundsInput) -> FundComparisonOutput:
        nav = self._calculate_nav_metrics(
            CalculateNavMetricsInput(
                fund_codes=[tool_input.fund_code_a, tool_input.fund_code_b],
                start_date=tool_input.start_date,
                end_date=tool_input.end_date,
            )
        )
        holdings = self._compare_holdings(
            CompareHoldingsInput(
                fund_code_a=tool_input.fund_code_a,
                fund_code_b=tool_input.fund_code_b,
                period=tool_input.period,
            )
        )
        by_code = {metric.fund_code: metric for metric in nav.metrics}
        left = by_code[tool_input.fund_code_a]
        right = by_code[tool_input.fund_code_b]
        return FundComparisonOutput(
            fund_code_a=tool_input.fund_code_a,
            fund_code_b=tool_input.fund_code_b,
            period=tool_input.period,
            common_start_date=nav.common_start_date,
            common_end_date=nav.common_end_date,
            nav_metrics=nav.metrics,
            cumulative_change_difference_a_minus_b=left.cumulative_change
            - right.cumulative_change,
            volatility_difference_a_minus_b=left.annualized_volatility
            - right.annualized_volatility,
            holdings=holdings,
        )

    def build_evidence_table(
        self, tool_input: BuildEvidenceTableInput, *, request_id: str
    ) -> EvidenceTableOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="build_evidence_table",
            tool_input=tool_input,
            handler=lambda: self._build_evidence_table(tool_input),
        )

    def _build_evidence_table(
        self, tool_input: BuildEvidenceTableInput
    ) -> EvidenceTableOutput:
        if len(tool_input.claims) > self.policy.config.maximum_claims_per_call:
            raise ToolError(ToolErrorCode.POLICY_VIOLATION, "too many claims")
        chunks = self.repository.jsonl_objects("chunks.jsonl")
        chunk_by_id = {str(row["chunk_id"]): row for row in chunks}
        rows: list[EvidenceTableRow] = []
        for claim in tool_input.claims:
            check = self._citation_check(claim.citation)
            chunk = chunk_by_id.get(claim.citation.chunk_id)
            exact = bool(
                chunk is not None
                and claim.evidence_excerpt in str(chunk.get("text", ""))
            )
            located = check.valid and exact
            rows.append(
                EvidenceTableRow(
                    claim_id=claim.claim_id,
                    claim_text=claim.claim_text,
                    evidence_excerpt=claim.evidence_excerpt,
                    chunk_id=claim.citation.chunk_id,
                    physical_page=claim.citation.physical_page,
                    citation_valid=check.valid,
                    exact_excerpt=exact,
                    status="LOCATED" if located else "REJECTED",
                    limitation="location_and_exact_excerpt_only_not_semantic_entailment",
                )
            )
        return EvidenceTableOutput(
            all_located=all(row.status == "LOCATED" for row in rows), rows=rows
        )

    def validate_numeric_claims(
        self, tool_input: ValidateNumericClaimsInput, *, request_id: str
    ) -> NumericValidationOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="validate_numeric_claims",
            tool_input=tool_input,
            handler=lambda: self._validate_numeric_claims(tool_input),
        )

    def _expected_numeric(self, claim: NumericClaimInput) -> float:
        self.policy.require_funds([claim.fund_code])
        nav_metrics = {"cumulative_change", "annualized_volatility", "max_drawdown"}
        holding_metrics = {"c10", "hhi10"}
        pair_holding_metrics = {"name_jaccard", "common_nav_share"}
        if claim.metric in nav_metrics:
            output = self._calculate_nav_metrics(
                CalculateNavMetricsInput(
                    fund_codes=[claim.fund_code],
                    start_date=claim.start_date,
                    end_date=claim.end_date,
                )
            )
            return float(getattr(output.metrics[0], claim.metric))
        if claim.metric in holding_metrics:
            if claim.period is None:
                raise ValueError("period is required")
            self.policy.require_periods([claim.period])
            rows = self._holding_rows(claim.fund_code, claim.period)
            weights = [Decimal(row["nav_ratio_pct"]) / Decimal(100) for row in rows]
            return float(c10(weights) if claim.metric == "c10" else hhi10(weights))
        if claim.metric in pair_holding_metrics:
            if claim.period is None or claim.comparison_fund_code is None:
                raise ValueError("period and comparison_fund_code are required")
            comparison = self._compare_holdings(
                CompareHoldingsInput(
                    fund_code_a=claim.fund_code,
                    fund_code_b=claim.comparison_fund_code,
                    period=claim.period,
                )
            )
            return float(getattr(comparison, claim.metric))
        if claim.metric == "pearson_correlation":
            if claim.comparison_fund_code is None:
                raise ValueError("comparison_fund_code is required")
            series = self._nav_series(
                [claim.fund_code, claim.comparison_fund_code],
                claim.start_date,
                claim.end_date,
            )
            left = simple_returns([item[1] for item in series[claim.fund_code]])
            right = simple_returns(
                [item[1] for item in series[claim.comparison_fund_code]]
            )
            return pearson_correlation(left, right)
        raise ValueError("metric is not supported")

    def _validate_numeric_claims(
        self, tool_input: ValidateNumericClaimsInput
    ) -> NumericValidationOutput:
        if len(tool_input.claims) > self.policy.config.maximum_claims_per_call:
            raise ToolError(ToolErrorCode.POLICY_VIOLATION, "too many claims")
        checks: list[NumericClaimCheck] = []
        for claim in tool_input.claims:
            try:
                expected = self._expected_numeric(claim)
            except ValueError as exc:
                checks.append(
                    NumericClaimCheck(
                        claim_id=claim.claim_id,
                        metric=claim.metric,
                        claimed_value=claim.claimed_value,
                        expected_value=None,
                        absolute_difference=None,
                        valid=False,
                        reason_code=str(exc),
                    )
                )
                continue
            difference = abs(claim.claimed_value - expected)
            valid = difference <= claim.absolute_tolerance
            checks.append(
                NumericClaimCheck(
                    claim_id=claim.claim_id,
                    metric=claim.metric,
                    claimed_value=claim.claimed_value,
                    expected_value=expected,
                    absolute_difference=difference,
                    valid=valid,
                    reason_code="verified" if valid else "numeric_mismatch",
                )
            )
        return NumericValidationOutput(
            all_valid=all(check.valid for check in checks), checks=checks
        )

    def export_research_memo(
        self, tool_input: ExportResearchMemoInput, *, request_id: str
    ) -> ExportResearchMemoOutput:
        return self.runtime.invoke(
            request_id=request_id,
            tool_name="export_research_memo",
            tool_input=tool_input,
            handler=lambda: self._export_research_memo(tool_input),
        )

    def _export_research_memo(
        self, tool_input: ExportResearchMemoInput
    ) -> ExportResearchMemoOutput:
        if not tool_input.human_approved:
            raise ToolError(
                ToolErrorCode.APPROVAL_REQUIRED,
                "formal export requires explicit human approval",
            )
        evidence_table = self._build_evidence_table(
            BuildEvidenceTableInput(claims=tool_input.evidence_claims)
        )
        numeric_validation = self._validate_numeric_claims(
            ValidateNumericClaimsInput(claims=tool_input.numeric_claims)
        )
        if not evidence_table.all_located:
            raise ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                "formal export requires a fully located evidence table",
            )
        if not numeric_validation.all_valid:
            raise ToolError(
                ToolErrorCode.POLICY_VIOLATION,
                "formal export requires valid numeric claims",
            )
        output_path = self.policy.export_path(tool_input.file_name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# {tool_input.title}\n\n"
            f"{tool_input.markdown_body.rstrip()}\n\n"
            "---\n"
            f"人工审批：{tool_input.approved_by}\n\n"
            f"审批编号：{tool_input.approval_id}\n"
        )
        payload = content.encode("utf-8")
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, output_path)
        relative_path = output_path.relative_to(self.policy.workspace_root).as_posix()
        return ExportResearchMemoOutput(
            status="EXPORTED",
            relative_path=relative_path,
            content_sha256=hashlib.sha256(payload).hexdigest(),
            evidence_table_sha256=hashlib.sha256(
                evidence_table.model_dump_json().encode("utf-8")
            ).hexdigest(),
            numeric_validation_sha256=hashlib.sha256(
                numeric_validation.model_dump_json().encode("utf-8")
            ).hexdigest(),
            approval_id=tool_input.approval_id,
            bytes_written=len(payload),
        )


def build_toolbox(
    *,
    config_path: Path = DEFAULT_PHASE6_CONFIG,
    workspace_root: Path = WORKSPACE_ROOT,
) -> FundToolbox:
    config = load_phase6_config(config_path)
    policy = ToolPolicy(config=config, workspace_root=workspace_root)
    sink = AuditSink()
    runtime = ToolRuntime(
        allowed_tools=set(config.allowed_tools),
        timeouts_seconds=config.tool_timeouts_seconds,
        audit_sink=sink,
    )
    return FundToolbox(
        policy=policy,
        repository=DatasetRepository(policy),
        runtime=runtime,
        audit_sink=sink,
    )
