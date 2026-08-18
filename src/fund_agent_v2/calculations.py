from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import TypedDict


class DrawdownResult(TypedDict):
    max_drawdown: float
    peak_date: date
    trough_date: date
    recovery_date: date | None


def validate_nav(values: Sequence[float]) -> None:
    if len(values) < 2:
        raise ValueError("at least two NAV observations are required")
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("NAV values must be finite and positive")


def simple_returns(values: Sequence[float]) -> list[float]:
    validate_nav(values)
    return [current / previous - 1.0 for previous, current in pairwise(values)]


def cumulative_change(values: Sequence[float]) -> float:
    validate_nav(values)
    return values[-1] / values[0] - 1.0


def sample_standard_deviation(values: Sequence[float]) -> float:
    if len(values) < 2:
        raise ValueError("sample standard deviation needs two observations")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def annualized_volatility(
    returns: Sequence[float], periods_per_year: int = 252
) -> float:
    return sample_standard_deviation(returns) * math.sqrt(periods_per_year)


def maximum_drawdown(dates: Sequence[date], values: Sequence[float]) -> DrawdownResult:
    if len(dates) != len(values):
        raise ValueError("dates and NAV values must have equal length")
    validate_nav(values)
    if any(current <= previous for previous, current in pairwise(dates)):
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


def pearson_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError(
            "correlation needs equal series with at least two observations"
        )
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_deviation = [value - left_mean for value in left]
    right_deviation = [value - right_mean for value in right]
    numerator = sum(a * b for a, b in zip(left_deviation, right_deviation))
    denominator = math.sqrt(
        sum(value * value for value in left_deviation)
        * sum(value * value for value in right_deviation)
    )
    if denominator == 0:
        raise ValueError("correlation is undefined for a constant series")
    return max(-1.0, min(1.0, numerator / denominator))


def c10(weights: Iterable[Decimal]) -> Decimal:
    values = list(weights)
    if len(values) != 10 or any(value < 0 for value in values):
        raise ValueError("C10 requires exactly ten non-negative weights")
    return sum(values, Decimal(0))


def hhi10(weights: Iterable[Decimal]) -> Decimal:
    values = list(weights)
    total = c10(values)
    if total <= 0:
        raise ValueError("HHI10 requires positive disclosed weight")
    return sum(((value / total) ** 2 for value in values), Decimal(0))


def name_jaccard(left: Iterable[str], right: Iterable[str]) -> Decimal:
    left_set = {value.strip() for value in left if value.strip()}
    right_set = {value.strip() for value in right if value.strip()}
    union = left_set | right_set
    if not union:
        raise ValueError("NameJaccard needs at least one disclosed name")
    return Decimal(len(left_set & right_set)) / Decimal(len(union))


def common_nav_share(
    left: Mapping[str, Decimal], right: Mapping[str, Decimal]
) -> Decimal:
    return sum(
        (min(left[code], right[code]) for code in set(left) & set(right)),
        Decimal(0),
    )
