from __future__ import annotations

import math
from datetime import date

import pytest

from fund_agent_v2.schemas import (
    CalculateNavMetricsInput,
    CompareFundsInput,
    CompareHoldingsInput,
    NumericClaimInput,
    ValidateNumericClaimsInput,
)
from fund_agent_v2.tools import FundToolbox

pytestmark = pytest.mark.local_data


def test_calculate_nav_metrics_matches_frozen_sample(toolbox: FundToolbox) -> None:
    result = toolbox.calculate_nav_metrics(
        CalculateNavMetricsInput(
            fund_codes=["SYN001", "SYN002", "SYN003"],
        ),
        request_id="nav-1",
    )
    by_code = {row.fund_code: row for row in result.metrics}
    assert result.common_start_date == date(2026, 1, 5)
    assert result.common_end_date == date(2026, 4, 24)
    assert result.common_observations == 80
    assert math.isclose(
        by_code["SYN001"].cumulative_change,
        0.09426000000000001,
        abs_tol=1.0e-15,
    )
    assert math.isclose(
        by_code["SYN002"].annualized_volatility,
        0.06083486177872739,
        abs_tol=1.0e-15,
    )
    assert math.isclose(
        by_code["SYN003"].max_drawdown,
        -0.06900364152306881,
        abs_tol=1.0e-15,
    )


def test_compare_holdings_matches_independent_expected_values(
    toolbox: FundToolbox,
) -> None:
    result = toolbox.compare_holdings(
        CompareHoldingsInput(
            fund_code_a="SYN002", fund_code_b="SYN001", period="2026Q1"
        ),
        request_id="holdings-1",
    )
    assert result.common_stock_codes == [
        "S00008", "S00009", "S00010", "S00011", "S00012"
    ]
    assert result.common_stock_count == 5
    assert math.isclose(result.name_jaccard, 1 / 3, abs_tol=1.0e-15)
    assert math.isclose(result.common_nav_share, 0.133, abs_tol=1.0e-15)
    assert math.isclose(result.fund_a.c10, 0.348, abs_tol=1.0e-15)


def test_compare_funds_composes_nav_and_holdings(toolbox: FundToolbox) -> None:
    result = toolbox.compare_funds(
        CompareFundsInput(fund_code_a="SYN002", fund_code_b="SYN001", period="2026Q2"),
        request_id="compare-1",
    )
    assert len(result.nav_metrics) == 2
    assert result.holdings.period == "2026Q2"
    assert result.common_start_date == date(2026, 1, 5)
    expected = (
        result.nav_metrics[0].cumulative_change
        - result.nav_metrics[1].cumulative_change
    )
    assert math.isclose(
        result.cumulative_change_difference_a_minus_b, expected, abs_tol=1.0e-15
    )


def test_validate_numeric_claims_recomputes_reference_values(
    toolbox: FundToolbox,
) -> None:
    result = toolbox.validate_numeric_claims(
        ValidateNumericClaimsInput(
            claims=[
                NumericClaimInput(
                    claim_id="nav-valid",
                    metric="cumulative_change",
                    claimed_value=0.09426000000000001,
                    fund_code="SYN001",
                ),
                NumericClaimInput(
                    claim_id="overlap-valid",
                    metric="common_nav_share",
                    claimed_value=0.133,
                    fund_code="SYN002",
                    comparison_fund_code="SYN001",
                    period="2026Q1",
                ),
                NumericClaimInput(
                    claim_id="nav-invalid",
                    metric="max_drawdown",
                    claimed_value=0.99,
                    fund_code="SYN002",
                ),
            ]
        ),
        request_id="numeric-1",
    )
    assert result.all_valid is False
    checks = {check.claim_id: check for check in result.checks}
    assert checks["nav-valid"].valid is True
    assert checks["overlap-valid"].valid is True
    assert checks["nav-invalid"].valid is False
    assert checks["nav-invalid"].reason_code == "numeric_mismatch"


def test_numeric_claim_with_missing_scope_is_rejected_in_result(
    toolbox: FundToolbox,
) -> None:
    result = toolbox.validate_numeric_claims(
        ValidateNumericClaimsInput(
            claims=[
                NumericClaimInput(
                    claim_id="missing-period",
                    metric="hhi10",
                    claimed_value=0.1,
                    fund_code="SYN001",
                )
            ]
        ),
        request_id="numeric-missing",
    )
    assert result.all_valid is False
    assert result.checks[0].expected_value is None
    assert result.checks[0].reason_code == "period is required"
