"""Pure F3 metric functions for NAV and public top-ten disclosures."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Iterable, Mapping, Sequence


TRADING_DAYS_PER_YEAR = 252


def _validate_values(values: Sequence[float]) -> None:
    if len(values) < 2:
        raise ValueError("at least two NAV observations are required")
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("NAV values must be finite and positive")


def calculate_simple_returns(values: Sequence[float]) -> list[float]:
    """Return observation-to-observation simple returns without date filling."""
    _validate_values(values)
    return [
        current / previous - 1.0
        for previous, current in zip(values, values[1:])
    ]


def cumulative_change(values: Sequence[float]) -> float:
    _validate_values(values)
    return values[-1] / values[0] - 1.0


def sample_standard_deviation(values: Sequence[float]) -> float:
    if len(values) < 2:
        raise ValueError("sample standard deviation needs two observations")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (
        len(values) - 1
    )
    return math.sqrt(variance)


def annualized_volatility(
    returns: Sequence[float],
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    return sample_standard_deviation(returns) * math.sqrt(
        periods_per_year
    )


def maximum_drawdown(
    dates: Sequence[date], values: Sequence[float]
) -> dict[str, object]:
    if len(dates) != len(values):
        raise ValueError("dates and NAV values must have equal length")
    _validate_values(values)
    if any(current <= previous for previous, current in zip(dates, dates[1:])):
        raise ValueError("NAV dates must be strictly increasing")

    peak_value = values[0]
    peak_index = 0
    maximum = 0.0
    drawdown_peak_index = 0
    trough_index = 0

    for index, value in enumerate(values):
        if value > peak_value:
            peak_value = value
            peak_index = index
        drawdown = value / peak_value - 1.0
        if drawdown < maximum:
            maximum = drawdown
            drawdown_peak_index = peak_index
            trough_index = index

    recovery_date: date | None = None
    peak_nav = values[drawdown_peak_index]
    for index in range(trough_index + 1, len(values)):
        if values[index] >= peak_nav:
            recovery_date = dates[index]
            break

    return {
        "max_drawdown": maximum,
        "peak_date": dates[drawdown_peak_index],
        "trough_date": dates[trough_index],
        "recovery_date": recovery_date,
    }


def pearson_correlation(
    left: Sequence[float], right: Sequence[float]
) -> float:
    if len(left) != len(right):
        raise ValueError("correlation series must have equal length")
    if len(left) < 2:
        raise ValueError("correlation needs two paired observations")
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_deviation = [value - left_mean for value in left]
    right_deviation = [value - right_mean for value in right]
    numerator = sum(
        left_value * right_value
        for left_value, right_value in zip(
            left_deviation, right_deviation
        )
    )
    left_sum = sum(value * value for value in left_deviation)
    right_sum = sum(value * value for value in right_deviation)
    denominator = math.sqrt(left_sum * right_sum)
    if denominator == 0:
        raise ValueError("correlation is undefined for a constant series")
    result = numerator / denominator
    return max(-1.0, min(1.0, result))


def c10(weights: Iterable[Decimal]) -> Decimal:
    values = list(weights)
    if len(values) != 10:
        raise ValueError("C10 requires exactly ten disclosed weights")
    if any(value < 0 for value in values):
        raise ValueError("holding weights cannot be negative")
    return sum(values, Decimal("0"))


def hhi10(weights: Iterable[Decimal]) -> Decimal:
    values = list(weights)
    total = c10(values)
    if total <= 0:
        raise ValueError("HHI10 requires positive disclosed weight")
    return sum(
        ((value / total) ** 2 for value in values),
        Decimal("0"),
    )


def name_jaccard(
    names_left: Iterable[str], names_right: Iterable[str]
) -> Decimal:
    left = {name.strip() for name in names_left if name.strip()}
    right = {name.strip() for name in names_right if name.strip()}
    union = left | right
    if not union:
        raise ValueError("NameJaccard needs at least one disclosed name")
    return Decimal(len(left & right)) / Decimal(len(union))


def common_nav_share(
    weights_left: Mapping[str, Decimal],
    weights_right: Mapping[str, Decimal],
) -> Decimal:
    common_codes = set(weights_left) & set(weights_right)
    return sum(
        (
            min(weights_left[code], weights_right[code])
            for code in common_codes
        ),
        Decimal("0"),
    )


def validate_same_period(period_left: str, period_right: str) -> None:
    if period_left != period_right:
        raise ValueError(
            "public top-ten holdings may only be compared "
            "within the same report period"
        )
