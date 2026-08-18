from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from typing import cast

from pydantic import BaseModel

from .errors import ToolError
from .guardrails import classify_request
from .phase7_schemas import (
    AgentResponse,
    AgentToolStep,
    FundAgentPhase7Config,
    ScopeDecision,
)
from .schemas import (
    BuildEvidenceTableInput,
    CalculateNavMetricsInput,
    CitationRef,
    CitationVerificationOutput,
    CompareFundsInput,
    CompareHoldingsInput,
    EvidenceClaimInput,
    EvidenceTableOutput,
    EvidenceTableRow,
    FundComparisonOutput,
    FundProfileOutput,
    HoldingsComparisonOutput,
    LoadFundProfileInput,
    NavMetricsOutput,
    NumericClaimCheck,
    NumericClaimInput,
    NumericMetricName,
    NumericValidationOutput,
    RetrievalOutput,
    RetrieveReportEvidenceInput,
    ValidateNumericClaimsInput,
    VerifyCitationsInput,
)
from .tools import FundToolbox


def _hash_model(model: BaseModel) -> str:
    return hashlib.sha256(model.model_dump_json().encode("utf-8")).hexdigest()


class DeterministicMockSingleAgent:
    """Offline state-machine surrogate for evaluating policy and tool wiring."""

    def __init__(self, *, config: FundAgentPhase7Config, toolbox: FundToolbox) -> None:
        self.config = config
        self.toolbox = toolbox

    def run(self, query: str, *, request_id: str | None = None) -> AgentResponse:
        started = time.perf_counter()
        effective_request_id = request_id or uuid.uuid4().hex
        decision = classify_request(
            query,
            allowed_funds=set(self.config.allowed_fund_codes),
            allowed_periods=set(self.config.allowed_periods),
            max_input_chars=self.config.max_input_chars,
        )
        steps: list[AgentToolStep] = []
        if not decision.allowed:
            return self._response(
                request_id=effective_request_id,
                status="REFUSED",
                answer="当前请求超出可验证的基金研究范围，已安全拒绝。",
                reasons=decision.reason_codes,
                steps=steps,
                started=started,
            )

        consecutive_failures = 0

        def call(
            tool_name: str,
            tool_input: BaseModel,
            handler: Callable[[], BaseModel],
        ) -> BaseModel:
            nonlocal consecutive_failures
            if len(steps) >= self.config.max_tool_steps:
                raise RuntimeError("TOOL_STEP_BUDGET_EXCEEDED")
            call_started = time.perf_counter()
            dumped = tool_input.model_dump(mode="json")
            fund_codes = self._scope_values(dumped, "fund")
            periods = self._scope_values(dumped, "period")
            try:
                output = handler()
            except ToolError as exc:
                consecutive_failures += 1
                steps.append(
                    AgentToolStep(
                        step=len(steps) + 1,
                        tool_name=tool_name,
                        status="ERROR",
                        duration_ms=(time.perf_counter() - call_started) * 1000.0,
                        input_sha256=_hash_model(tool_input),
                        output_sha256=None,
                        fund_codes=fund_codes,
                        periods=periods,
                        error_code=exc.code.value,
                    )
                )
                raise
            consecutive_failures = 0
            steps.append(
                AgentToolStep(
                    step=len(steps) + 1,
                    tool_name=tool_name,
                    status="SUCCESS",
                    duration_ms=(time.perf_counter() - call_started) * 1000.0,
                    input_sha256=_hash_model(tool_input),
                    output_sha256=_hash_model(output),
                    fund_codes=fund_codes,
                    periods=periods,
                    error_code=None,
                )
            )
            return output

        try:
            return self._dispatch(
                query=query,
                request_id=effective_request_id,
                decision=decision,
                steps=steps,
                started=started,
                call=call,
            )
        except (ToolError, RuntimeError) as exc:
            reason = str(exc) or type(exc).__name__
            if consecutive_failures >= self.config.max_consecutive_tool_failures:
                reason = "CONSECUTIVE_TOOL_FAILURE_LIMIT"
            return self._response(
                request_id=effective_request_id,
                status="ERROR",
                answer="工具执行未能安全完成，未生成研究结论。",
                reasons=[reason],
                steps=steps,
                started=started,
            )

    @staticmethod
    def _scope_values(payload: dict[str, object], kind: str) -> list[str]:
        values: list[str] = []
        for key, value in payload.items():
            if kind not in key:
                continue
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(item) for item in value)
        return sorted(set(values))

    def _dispatch(
        self,
        *,
        query: str,
        request_id: str,
        decision: ScopeDecision,
        steps: list[AgentToolStep],
        started: float,
        call: Callable[[str, BaseModel, Callable[[], BaseModel]], BaseModel],
    ) -> AgentResponse:
        if decision.intent == "PROFILE":
            profile_input = LoadFundProfileInput(profile="demo_synthetic")
            profile = cast(
                FundProfileOutput,
                call(
                    "load_fund_profile",
                    profile_input,
                    lambda: self.toolbox.load_fund_profile(
                        profile_input, request_id=request_id
                    ),
                ),
            )
            answer = (
                f"当前可研究基金为 {', '.join(profile.fund_codes)}；"
                f"报告期为 {', '.join(profile.periods)}。"
            )
            return self._response(
                request_id=request_id,
                status="ANSWERED",
                answer=answer,
                reasons=["PROFILE_LOADED"],
                steps=steps,
                started=started,
            )

        if decision.intent == "NAV":
            if not decision.fund_codes:
                return self._refuse_missing_scope(request_id, steps, started)
            nav_input = CalculateNavMetricsInput(fund_codes=decision.fund_codes)
            nav = cast(
                NavMetricsOutput,
                call(
                    "calculate_nav_metrics",
                    nav_input,
                    lambda: self.toolbox.calculate_nav_metrics(
                        nav_input, request_id=request_id
                    ),
                ),
            )
            metric_names: list[NumericMetricName] = [
                "cumulative_change",
                "annualized_volatility",
                "max_drawdown",
            ]
            claims = [
                NumericClaimInput(
                    claim_id=f"{metric.fund_code}-{name}",
                    metric=name,
                    claimed_value=float(getattr(metric, name)),
                    fund_code=metric.fund_code,
                )
                for metric in nav.metrics
                for name in metric_names
            ]
            validation_input = ValidateNumericClaimsInput(claims=claims)
            validation = cast(
                NumericValidationOutput,
                call(
                    "validate_numeric_claims",
                    validation_input,
                    lambda: self.toolbox.validate_numeric_claims(
                        validation_input, request_id=request_id
                    ),
                ),
            )
            answer = "；".join(
                f"{metric.fund_code} 累计收益 {metric.cumulative_change:.6f}，"
                f"年化波动 {metric.annualized_volatility:.6f}，"
                f"最大回撤 {metric.max_drawdown:.6f}"
                for metric in nav.metrics
            )
            return self._response(
                request_id=request_id,
                status="ANSWERED",
                answer=answer,
                reasons=["NUMERICALLY_VERIFIED"],
                steps=steps,
                started=started,
                numeric_checks=validation.checks,
            )

        if decision.intent == "HOLDINGS":
            if len(decision.fund_codes) != 2 or len(decision.periods) != 1:
                return self._refuse_missing_scope(request_id, steps, started)
            holdings_input = CompareHoldingsInput(
                fund_code_a=decision.fund_codes[0],
                fund_code_b=decision.fund_codes[1],
                period=decision.periods[0],
            )
            holdings = cast(
                HoldingsComparisonOutput,
                call(
                    "compare_holdings",
                    holdings_input,
                    lambda: self.toolbox.compare_holdings(
                        holdings_input, request_id=request_id
                    ),
                ),
            )
            claims = [
                NumericClaimInput(
                    claim_id="name-jaccard",
                    metric="name_jaccard",
                    claimed_value=holdings.name_jaccard,
                    fund_code=holdings.fund_a.fund_code,
                    comparison_fund_code=holdings.fund_b.fund_code,
                    period=holdings.period,
                ),
                NumericClaimInput(
                    claim_id="common-nav-share",
                    metric="common_nav_share",
                    claimed_value=holdings.common_nav_share,
                    fund_code=holdings.fund_a.fund_code,
                    comparison_fund_code=holdings.fund_b.fund_code,
                    period=holdings.period,
                ),
            ]
            validation_input = ValidateNumericClaimsInput(claims=claims)
            validation = cast(
                NumericValidationOutput,
                call(
                    "validate_numeric_claims",
                    validation_input,
                    lambda: self.toolbox.validate_numeric_claims(
                        validation_input, request_id=request_id
                    ),
                ),
            )
            answer = (
                f"{holdings.period} 两基金公开前十大持仓的 "
                f"NameJaccard={holdings.name_jaccard:.6f}，"
                f"CommonNAVShare={holdings.common_nav_share:.6f}。"
            )
            return self._response(
                request_id=request_id,
                status="ANSWERED",
                answer=answer,
                reasons=["HOLDINGS_NUMERICALLY_VERIFIED"],
                steps=steps,
                started=started,
                numeric_checks=validation.checks,
            )

        if decision.intent == "COMPARE":
            if len(decision.fund_codes) != 2 or len(decision.periods) != 1:
                return self._refuse_missing_scope(request_id, steps, started)
            comparison_input = CompareFundsInput(
                fund_code_a=decision.fund_codes[0],
                fund_code_b=decision.fund_codes[1],
                period=decision.periods[0],
            )
            comparison = cast(
                FundComparisonOutput,
                call(
                    "compare_funds",
                    comparison_input,
                    lambda: self.toolbox.compare_funds(
                        comparison_input, request_id=request_id
                    ),
                ),
            )
            validation_input = ValidateNumericClaimsInput(
                claims=[
                    NumericClaimInput(
                        claim_id=f"compare-{metric.fund_code}",
                        metric="cumulative_change",
                        claimed_value=metric.cumulative_change,
                        fund_code=metric.fund_code,
                    )
                    for metric in comparison.nav_metrics
                ]
                + [
                    NumericClaimInput(
                        claim_id="compare-name-jaccard",
                        metric="name_jaccard",
                        claimed_value=comparison.holdings.name_jaccard,
                        fund_code=comparison.fund_code_a,
                        comparison_fund_code=comparison.fund_code_b,
                        period=comparison.period,
                    ),
                    NumericClaimInput(
                        claim_id="compare-common-nav-share",
                        metric="common_nav_share",
                        claimed_value=comparison.holdings.common_nav_share,
                        fund_code=comparison.fund_code_a,
                        comparison_fund_code=comparison.fund_code_b,
                        period=comparison.period,
                    ),
                ]
            )
            validation = cast(
                NumericValidationOutput,
                call(
                    "validate_numeric_claims",
                    validation_input,
                    lambda: self.toolbox.validate_numeric_claims(
                        validation_input, request_id=request_id
                    ),
                ),
            )
            answer = (
                f"共同窗口内 {comparison.fund_code_a} 累计收益为 "
                f"{comparison.nav_metrics[0].cumulative_change:.6f}，"
                f"{comparison.fund_code_b} 累计收益为 "
                f"{comparison.nav_metrics[1].cumulative_change:.6f}；"
                f"{comparison.period} 公开前十大持仓 NameJaccard="
                f"{comparison.holdings.name_jaccard:.6f}，CommonNAVShare="
                f"{comparison.holdings.common_nav_share:.6f}。"
            )
            return self._response(
                request_id=request_id,
                status="ANSWERED",
                answer=answer,
                reasons=["STRUCTURED_COMPARISON_VERIFIED"],
                steps=steps,
                started=started,
                numeric_checks=validation.checks,
            )

        if decision.intent == "EVIDENCE":
            if not decision.fund_codes or not decision.periods:
                return self._refuse_missing_scope(request_id, steps, started)
            retrieval_input = RetrieveReportEvidenceInput(
                query=query,
                fund_codes=decision.fund_codes,
                periods=decision.periods,
                top_k=3,
            )
            retrieval = cast(
                RetrievalOutput,
                call(
                    "retrieve_report_evidence",
                    retrieval_input,
                    lambda: self.toolbox.retrieve_report_evidence(
                        retrieval_input, request_id=request_id
                    ),
                ),
            )
            if (
                not retrieval.cards
                or retrieval.cards[0].score < self.config.minimum_evidence_score
            ):
                return self._response(
                    request_id=request_id,
                    status="REFUSED",
                    answer="当前注册文档没有足够证据回答该问题。",
                    reasons=["INSUFFICIENT_EVIDENCE"],
                    steps=steps,
                    started=started,
                )
            citation_input = VerifyCitationsInput(
                citations=[card.citation for card in retrieval.cards]
            )
            citation_output = cast(
                CitationVerificationOutput,
                call(
                    "verify_citations",
                    citation_input,
                    lambda: self.toolbox.verify_citations(
                        citation_input, request_id=request_id
                    ),
                ),
            )
            if not citation_output.all_valid:
                return self._response(
                    request_id=request_id,
                    status="REFUSED",
                    answer="引用完整性验证失败，未生成结论。",
                    reasons=["CITATION_VERIFICATION_FAILED"],
                    steps=steps,
                    started=started,
                )
            card = retrieval.cards[0]
            evidence_input = BuildEvidenceTableInput(
                claims=[
                    EvidenceClaimInput(
                        claim_id="answer-evidence-1",
                        claim_text="报告披露了相关投资方向。",
                        evidence_excerpt=card.evidence_text,
                        citation=card.citation,
                    )
                ]
            )
            evidence_output = cast(
                EvidenceTableOutput,
                call(
                    "build_evidence_table",
                    evidence_input,
                    lambda: self.toolbox.build_evidence_table(
                        evidence_input, request_id=request_id
                    ),
                ),
            )
            if not evidence_output.all_located:
                return self._response(
                    request_id=request_id,
                    status="REFUSED",
                    answer="证据无法精确定位，未生成结论。",
                    reasons=["EVIDENCE_LOCATION_FAILED"],
                    steps=steps,
                    started=started,
                )
            answer = (
                f"报告原文：{card.evidence_text}"
                f"（{card.citation.doc_id}，物理页 {card.citation.physical_page}）。"
            )
            return self._response(
                request_id=request_id,
                status="ANSWERED",
                answer=answer,
                reasons=["CITATION_AND_EXCERPT_VERIFIED"],
                steps=steps,
                started=started,
                citations=[card.citation],
                evidence_rows=evidence_output.rows,
            )

        return self._response(
            request_id=request_id,
            status="REFUSED",
            answer="当前问题不在已注册工具能力范围内。",
            reasons=["UNSUPPORTED_QUESTION"],
            steps=steps,
            started=started,
        )

    def _refuse_missing_scope(
        self, request_id: str, steps: list[AgentToolStep], started: float
    ) -> AgentResponse:
        return self._response(
            request_id=request_id,
            status="REFUSED",
            answer="问题缺少基金代码或报告期，无法进行受控研究。",
            reasons=["MISSING_REQUIRED_SCOPE"],
            steps=steps,
            started=started,
        )

    def _response(
        self,
        *,
        request_id: str,
        status: str,
        answer: str,
        reasons: list[str],
        steps: list[AgentToolStep],
        started: float,
        citations: list[CitationRef] | None = None,
        numeric_checks: list[NumericClaimCheck] | None = None,
        evidence_rows: list[EvidenceTableRow] | None = None,
    ) -> AgentResponse:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return AgentResponse.model_validate(
            {
                "request_id": request_id,
                "status": status,
                "answer": answer[: self.config.max_output_chars],
                "reason_codes": reasons,
                "citations": citations or [],
                "numeric_checks": numeric_checks or [],
                "evidence_rows": evidence_rows or [],
                "tool_steps": steps,
                "usage": {
                    "provider": "DETERMINISTIC_MOCK",
                    "model": "deterministic-mock-v1",
                    "model_calls": 0,
                    "network_requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "elapsed_ms": elapsed_ms,
                },
            }
        )
