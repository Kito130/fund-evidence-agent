from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pytest

from fund_agent_v2.errors import ToolError, ToolErrorCode
from fund_agent_v2.schemas import (
    BuildEvidenceTableInput,
    EvidenceClaimInput,
    ExportResearchMemoInput,
    NumericClaimInput,
    RetrieveReportEvidenceInput,
    ValidateNumericClaimsInput,
)
from fund_agent_v2.tools import FundToolbox

pytestmark = pytest.mark.local_data


class ExportClaims(NamedTuple):
    evidence: list[EvidenceClaimInput]
    numeric: list[NumericClaimInput]


def _approved_inputs(toolbox: FundToolbox) -> ExportClaims:
    retrieval = toolbox.retrieve_report_evidence(
        RetrieveReportEvidenceInput(
            query="市场震荡和分散配置",
            fund_codes=["SYN001"],
            periods=["2026Q1"],
            top_k=1,
        ),
        request_id="export-retrieve",
    )
    card = retrieval.cards[0]
    evidence_claims = [
        EvidenceClaimInput(
            claim_id="export-evidence",
            claim_text="合成报告提及市场震荡和分散配置。",
            evidence_excerpt=card.evidence_text[:12],
            citation=card.citation,
        )
    ]
    evidence = toolbox.build_evidence_table(
        BuildEvidenceTableInput(claims=evidence_claims),
        request_id="export-evidence",
    )
    numeric_claims = [
        NumericClaimInput(
            claim_id="export-number",
            metric="cumulative_change",
            claimed_value=0.09426000000000001,
            fund_code="SYN001",
        )
    ]
    numeric = toolbox.validate_numeric_claims(
        ValidateNumericClaimsInput(claims=numeric_claims),
        request_id="export-numeric",
    )
    assert evidence.all_located and numeric.all_valid
    return ExportClaims(evidence=evidence_claims, numeric=numeric_claims)


def test_export_requires_human_approval_and_bounded_path(
    toolbox: FundToolbox,
) -> None:
    claims = _approved_inputs(toolbox)
    denied_input = ExportResearchMemoInput(
        file_name="phase6_pytest_memo.md",
        title="Phase 6 测试 Memo",
        markdown_body="这是经过工具验证的测试内容。",
        evidence_claims=claims.evidence,
        numeric_claims=claims.numeric,
        human_approved=False,
        approved_by="unit-test-user",
        approval_id="approval_test_001",
    )
    with pytest.raises(ToolError) as captured:
        toolbox.export_research_memo(denied_input, request_id="export-denied")
    assert captured.value.code == ToolErrorCode.APPROVAL_REQUIRED

    approved = denied_input.model_copy(update={"human_approved": True})
    result = toolbox.export_research_memo(approved, request_id="export-approved")
    output_path = toolbox.policy.workspace_root / result.relative_path
    try:
        assert result.status == "EXPORTED"
        assert output_path.is_relative_to(toolbox.policy.export_root)
        assert output_path.read_text(encoding="utf-8").startswith("# Phase 6")
    finally:
        if output_path == Path(toolbox.policy.export_root) / approved.file_name:
            output_path.unlink(missing_ok=True)
