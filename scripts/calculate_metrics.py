"""F3 metric calculation from the frozen F2 NAV and disclosure tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.metrics import (  # noqa: E402
    TRADING_DAYS_PER_YEAR,
    annualized_volatility,
    c10,
    calculate_simple_returns,
    common_nav_share,
    cumulative_change,
    hhi10,
    maximum_drawdown,
    name_jaccard,
    pearson_correlation,
    validate_same_period,
)


FUNDS = (
    ("003567", "华夏行业景气混合A"),
    ("003834", "华夏能源革新股票A"),
    ("002980", "华夏创新前沿股票"),
)
PERIODS = ("2025Q3", "2025Q4", "2026Q1", "2026Q2")

DEFAULT_NAV = PROJECT_ROOT / "data" / "curated" / "nav_daily.csv"
DEFAULT_TOP10 = (
    PROJECT_ROOT / "data" / "curated" / "top10_holdings.csv"
)
DEFAULT_F2_AUDIT = PROJECT_ROOT / "results" / "f2_audit.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_METRICS_JSON = PROJECT_ROOT / "results" / "metrics.json"
DEFAULT_AUDIT = PROJECT_ROOT / "results" / "f3_metrics_audit.json"
DEFAULT_RUN_MANIFEST = PROJECT_ROOT / "results" / "f3_run_manifest.json"

RETURN_FIELDS = (
    "fund_code",
    "fund_name",
    "date",
    "previous_date",
    "gap_calendar_days",
    "simple_return",
    "nav_field",
    "current_response_sha256",
    "previous_response_sha256",
)

NAV_METRIC_FIELDS = (
    "fund_code",
    "fund_name",
    "start_date",
    "end_date",
    "nav_observations",
    "return_observations",
    "cumulative_change",
    "annualized_volatility",
    "max_drawdown",
    "drawdown_peak_date",
    "drawdown_trough_date",
    "drawdown_recovery_date",
    "nav_field",
    "trading_days_per_year",
    "input_sha256",
)

CORRELATION_FIELDS = (
    "fund_code_a",
    "fund_name_a",
    "fund_code_b",
    "fund_name_b",
    "start_return_date",
    "end_return_date",
    "paired_observations",
    "pearson_correlation",
    "input_sha256",
)

HOLDING_METRIC_FIELDS = (
    "doc_id",
    "fund_code",
    "fund_name",
    "period",
    "period_end",
    "disclosed_holding_count",
    "c10",
    "hhi10",
    "terminology",
    "source_pdf_sha256",
    "input_sha256",
)

OVERLAP_FIELDS = (
    "period",
    "period_end",
    "fund_code_a",
    "fund_name_a",
    "fund_code_b",
    "fund_name_b",
    "common_stock_count",
    "name_intersection_count",
    "name_union_count",
    "name_jaccard",
    "common_nav_share",
    "common_stock_codes",
    "doc_id_a",
    "doc_id_b",
    "source_pdf_sha256_a",
    "source_pdf_sha256_b",
    "terminology",
    "input_sha256",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp_path, path)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def float_text(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("metric output is not finite")
    return format(value, ".17g")


def validate_f2_gate(path: Path) -> None:
    audit = json.loads(path.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS":
        raise ValueError("F2 must pass before F3 metrics are calculated")


def load_nav_series(
    path: Path,
) -> tuple[
    dict[str, list[dict[str, str]]],
    str,
]:
    rows = read_csv(path)
    if len(rows) != 1455:
        raise ValueError(f"expected 1455 frozen NAV rows, got {len(rows)}")
    expected_codes = {code for code, _ in FUNDS}
    if {row["fund_code"] for row in rows} != expected_codes:
        raise ValueError("NAV file does not contain the fixed three funds")
    keys = [(row["fund_code"], row["date"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("NAV dates are not unique within fund")
    if any(row["unit_nav"] != row["cumulative_nav"] for row in rows):
        raise ValueError(
            "unit and cumulative NAV diverge from the verified F2 basis"
        )

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["fund_code"]].append(row)
    date_sets = []
    for fund_code, fund_name in FUNDS:
        series = sorted(grouped[fund_code], key=lambda item: item["date"])
        if len(series) != 485:
            raise ValueError(f"{fund_code}: expected 485 NAV observations")
        if {item["fund_name"] for item in series} != {fund_name}:
            raise ValueError(f"{fund_code}: unstable fund name")
        dates = [date.fromisoformat(item["date"]) for item in series]
        if any(
            current <= previous
            for previous, current in zip(dates, dates[1:])
        ):
            raise ValueError(f"{fund_code}: NAV dates are not increasing")
        if any(Decimal(item["cumulative_nav"]) <= 0 for item in series):
            raise ValueError(f"{fund_code}: non-positive cumulative NAV")
        grouped[fund_code] = series
        date_sets.append({item["date"] for item in series})
    if len({frozenset(items) for items in date_sets}) != 1:
        raise ValueError("funds do not share the same frozen NAV dates")
    return dict(grouped), sha256_file(path)


def load_top10(
    path: Path,
) -> tuple[dict[tuple[str, str], list[dict[str, str]]], str]:
    rows = read_csv(path)
    if len(rows) != 120:
        raise ValueError(f"expected 120 public top-ten rows, got {len(rows)}")
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(
        list
    )
    for row in rows:
        grouped[(row["fund_code"], row["period"])].append(row)
    expected = {
        (fund_code, period)
        for fund_code, _ in FUNDS
        for period in PERIODS
    }
    if set(grouped) != expected:
        raise ValueError("public top-ten table is not the fixed 3 x 4 matrix")
    for key, items in grouped.items():
        items.sort(key=lambda item: int(item["public_holding_rank"]))
        ranks = [int(item["public_holding_rank"]) for item in items]
        if ranks != list(range(1, 11)):
            raise ValueError(f"{key}: public top-ten ranks are incomplete")
        if len({item["stock_code"] for item in items}) != 10:
            raise ValueError(f"{key}: duplicate disclosed stock code")
    return dict(grouped), sha256_file(path)


def calculate_nav_outputs(
    grouped: dict[str, list[dict[str, str]]],
    input_sha: str,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict],
    list[dict],
]:
    return_rows: list[dict[str, str]] = []
    metric_rows: list[dict[str, str]] = []
    correlation_rows: list[dict[str, str]] = []
    metric_json_rows: list[dict] = []
    correlation_json_rows: list[dict] = []
    returns_by_fund: dict[str, dict[str, float]] = {}

    for fund_code, fund_name in FUNDS:
        series = grouped[fund_code]
        dates = [date.fromisoformat(item["date"]) for item in series]
        values = [float(item["cumulative_nav"]) for item in series]
        returns = calculate_simple_returns(values)
        returns_by_fund[fund_code] = {
            item["date"]: return_value
            for item, return_value in zip(series[1:], returns)
        }
        for previous, current, return_value in zip(
            series, series[1:], returns
        ):
            previous_date = date.fromisoformat(previous["date"])
            current_date = date.fromisoformat(current["date"])
            return_rows.append(
                {
                    "fund_code": fund_code,
                    "fund_name": fund_name,
                    "date": current["date"],
                    "previous_date": previous["date"],
                    "gap_calendar_days": str(
                        (current_date - previous_date).days
                    ),
                    "simple_return": float_text(return_value),
                    "nav_field": "cumulative_nav",
                    "current_response_sha256": current[
                        "source_response_sha256"
                    ],
                    "previous_response_sha256": previous[
                        "source_response_sha256"
                    ],
                }
            )

        drawdown = maximum_drawdown(dates, values)
        cumulative = cumulative_change(values)
        volatility = annualized_volatility(returns)
        recovery = drawdown["recovery_date"]
        metric = {
            "fund_code": fund_code,
            "fund_name": fund_name,
            "start_date": dates[0].isoformat(),
            "end_date": dates[-1].isoformat(),
            "nav_observations": len(values),
            "return_observations": len(returns),
            "cumulative_change": cumulative,
            "annualized_volatility": volatility,
            "max_drawdown": drawdown["max_drawdown"],
            "drawdown_peak_date": drawdown["peak_date"].isoformat(),
            "drawdown_trough_date": drawdown["trough_date"].isoformat(),
            "drawdown_recovery_date": (
                recovery.isoformat() if recovery is not None else None
            ),
            "nav_field": "cumulative_nav",
            "trading_days_per_year": TRADING_DAYS_PER_YEAR,
            "input_sha256": input_sha,
        }
        metric_json_rows.append(metric)
        metric_rows.append(
            {
                key: (
                    ""
                    if value is None
                    else float_text(value)
                    if isinstance(value, float)
                    else str(value)
                )
                for key, value in metric.items()
            }
        )

    fund_names = dict(FUNDS)
    for code_a, _ in FUNDS:
        for code_b, _ in FUNDS:
            common_dates = sorted(
                set(returns_by_fund[code_a])
                & set(returns_by_fund[code_b])
            )
            left = [returns_by_fund[code_a][item] for item in common_dates]
            right = [
                returns_by_fund[code_b][item] for item in common_dates
            ]
            correlation = pearson_correlation(left, right)
            item = {
                "fund_code_a": code_a,
                "fund_name_a": fund_names[code_a],
                "fund_code_b": code_b,
                "fund_name_b": fund_names[code_b],
                "start_return_date": common_dates[0],
                "end_return_date": common_dates[-1],
                "paired_observations": len(common_dates),
                "pearson_correlation": correlation,
                "input_sha256": input_sha,
            }
            correlation_json_rows.append(item)
            correlation_rows.append(
                {
                    key: (
                        float_text(value)
                        if isinstance(value, float)
                        else str(value)
                    )
                    for key, value in item.items()
                }
            )

    return (
        return_rows,
        metric_rows,
        correlation_rows,
        metric_json_rows,
        correlation_json_rows,
    )


def calculate_holding_outputs(
    grouped: dict[tuple[str, str], list[dict[str, str]]],
    input_sha: str,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict],
    list[dict],
]:
    holding_rows: list[dict[str, str]] = []
    overlap_rows: list[dict[str, str]] = []
    holding_json_rows: list[dict] = []
    overlap_json_rows: list[dict] = []
    fund_names = dict(FUNDS)

    for fund_code, _ in FUNDS:
        for period in PERIODS:
            items = grouped[(fund_code, period)]
            weights = [
                Decimal(item["nav_ratio_pct"]) / Decimal("100")
                for item in items
            ]
            c10_value = c10(weights)
            hhi_value = hhi10(weights)
            first = items[0]
            item = {
                "doc_id": first["doc_id"],
                "fund_code": fund_code,
                "fund_name": first["fund_name"],
                "period": period,
                "period_end": first["period_end"],
                "disclosed_holding_count": 10,
                "c10": float(c10_value),
                "hhi10": float(hhi_value),
                "terminology": "公开前十大持仓",
                "source_pdf_sha256": first["source_pdf_sha256"],
                "input_sha256": input_sha,
            }
            holding_json_rows.append(item)
            holding_rows.append(
                {
                    key: (
                        float_text(value)
                        if isinstance(value, float)
                        else str(value)
                    )
                    for key, value in item.items()
                }
            )

    for period in PERIODS:
        for (code_a, _), (code_b, _) in itertools.combinations(FUNDS, 2):
            validate_same_period(period, period)
            left = grouped[(code_a, period)]
            right = grouped[(code_b, period)]
            left_by_code = {
                item["stock_code"]: Decimal(item["nav_ratio_pct"])
                / Decimal("100")
                for item in left
            }
            right_by_code = {
                item["stock_code"]: Decimal(item["nav_ratio_pct"])
                / Decimal("100")
                for item in right
            }
            left_names = {item["stock_name"] for item in left}
            right_names = {item["stock_name"] for item in right}
            common_codes = sorted(set(left_by_code) & set(right_by_code))
            jaccard_value = name_jaccard(left_names, right_names)
            common_share = common_nav_share(left_by_code, right_by_code)
            first_left = left[0]
            first_right = right[0]
            item = {
                "period": period,
                "period_end": first_left["period_end"],
                "fund_code_a": code_a,
                "fund_name_a": fund_names[code_a],
                "fund_code_b": code_b,
                "fund_name_b": fund_names[code_b],
                "common_stock_count": len(common_codes),
                "name_intersection_count": len(left_names & right_names),
                "name_union_count": len(left_names | right_names),
                "name_jaccard": float(jaccard_value),
                "common_nav_share": float(common_share),
                "doc_id_a": first_left["doc_id"],
                "doc_id_b": first_right["doc_id"],
                "source_pdf_sha256_a": first_left["source_pdf_sha256"],
                "source_pdf_sha256_b": first_right[
                    "source_pdf_sha256"
                ],
                "terminology": "公开前十大持仓重合",
                "input_sha256": input_sha,
            }
            overlap_json_rows.append(item)
            overlap_rows.append(
                {
                    **{
                        key: (
                            float_text(value)
                            if isinstance(value, float)
                            else str(value)
                        )
                        for key, value in item.items()
                    },
                    "common_stock_codes": "|".join(common_codes),
                }
            )
    return (
        holding_rows,
        overlap_rows,
        holding_json_rows,
        overlap_json_rows,
    )


def build_audit(
    *,
    return_rows: list[dict[str, str]],
    nav_metrics: list[dict],
    correlations: list[dict],
    holding_metrics: list[dict],
    overlaps: list[dict],
) -> dict:
    return_counts = Counter(item["fund_code"] for item in return_rows)
    correlation_map = {
        (item["fund_code_a"], item["fund_code_b"]): item[
            "pearson_correlation"
        ]
        for item in correlations
    }
    checks = {
        "return_rows_484_per_fund": (
            set(return_counts) == {code for code, _ in FUNDS}
            and set(return_counts.values()) == {484}
        ),
        "returns_use_observed_dates_only": all(
            int(item["gap_calendar_days"]) >= 1 for item in return_rows
        ),
        "nav_metric_rows_3": len(nav_metrics) == 3,
        "nav_metrics_finite": all(
            math.isfinite(item[field])
            for item in nav_metrics
            for field in (
                "cumulative_change",
                "annualized_volatility",
                "max_drawdown",
            )
        ),
        "max_drawdowns_nonpositive": all(
            item["max_drawdown"] <= 0 for item in nav_metrics
        ),
        "correlation_matrix_3_by_3": len(correlations) == 9,
        "correlation_diagonal_one": all(
            abs(correlation_map[(code, code)] - 1.0) <= 1e-12
            for code, _ in FUNDS
        ),
        "correlation_matrix_symmetric": all(
            abs(
                correlation_map[(code_a, code_b)]
                - correlation_map[(code_b, code_a)]
            )
            <= 1e-12
            for code_a, _ in FUNDS
            for code_b, _ in FUNDS
        ),
        "holding_metric_rows_12": len(holding_metrics) == 12,
        "holding_metric_ranges_valid": all(
            0 < item["c10"] <= 1
            and Decimal("0.1") <= Decimal(str(item["hhi10"])) <= 1
            for item in holding_metrics
        ),
        "same_period_overlap_rows_12": (
            len(overlaps) == 12
            and all(
                item["doc_id_a"].endswith(item["period"])
                and item["doc_id_b"].endswith(item["period"])
                for item in overlaps
            )
        ),
        "overlap_metric_ranges_valid": all(
            0 <= item["name_jaccard"] <= 1
            and 0 <= item["common_nav_share"] <= 1
            for item in overlaps
        ),
        "required_disclosure_terminology": all(
            item["terminology"] == "公开前十大持仓重合"
            for item in overlaps
        ),
    }
    return {
        "stage": "F3_METRICS",
        "generated_at": utc_now(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "counts": {
            "return_rows": len(return_rows),
            "nav_metric_rows": len(nav_metrics),
            "correlation_rows": len(correlations),
            "holding_metric_rows": len(holding_metrics),
            "public_top10_overlap_rows": len(overlaps),
        },
        "checks": checks,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nav-input", type=Path, default=DEFAULT_NAV)
    parser.add_argument("--top10-input", type=Path, default=DEFAULT_TOP10)
    parser.add_argument("--f2-audit", type=Path, default=DEFAULT_F2_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--metrics-json", type=Path, default=DEFAULT_METRICS_JSON
    )
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument(
        "--run-manifest", type=Path, default=DEFAULT_RUN_MANIFEST
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_f2_gate(args.f2_audit.resolve())
    nav_grouped, nav_sha = load_nav_series(args.nav_input.resolve())
    top10_grouped, top10_sha = load_top10(args.top10_input.resolve())

    (
        return_rows,
        nav_metric_rows,
        correlation_rows,
        nav_metric_json,
        correlation_json,
    ) = calculate_nav_outputs(nav_grouped, nav_sha)
    (
        holding_rows,
        overlap_rows,
        holding_json,
        overlap_json,
    ) = calculate_holding_outputs(top10_grouped, top10_sha)

    output_dir = args.output_dir.resolve()
    output_paths = {
        "nav_returns": output_dir / "nav_returns.csv",
        "nav_metrics": output_dir / "nav_metrics.csv",
        "return_correlation": output_dir / "return_correlation.csv",
        "holding_metrics": output_dir / "holding_metrics.csv",
        "public_top10_overlap": (
            output_dir / "public_top10_overlap.csv"
        ),
    }
    write_csv(output_paths["nav_returns"], RETURN_FIELDS, return_rows)
    write_csv(
        output_paths["nav_metrics"], NAV_METRIC_FIELDS, nav_metric_rows
    )
    write_csv(
        output_paths["return_correlation"],
        CORRELATION_FIELDS,
        correlation_rows,
    )
    write_csv(
        output_paths["holding_metrics"],
        HOLDING_METRIC_FIELDS,
        holding_rows,
    )
    write_csv(
        output_paths["public_top10_overlap"],
        OVERLAP_FIELDS,
        overlap_rows,
    )

    generated_at = utc_now()
    metrics_payload = {
        "stage": "F3",
        "schema_version": "f3_metrics_v1",
        "generated_at": generated_at,
        "conventions": {
            "nav_field": "cumulative_nav",
            "return_type": "simple observation-to-observation return",
            "calendar_fill": False,
            "annualization_factor": TRADING_DAYS_PER_YEAR,
            "volatility_ddof": 1,
            "max_drawdown_sign": "non-positive",
            "c10_unit": "share_of_fund_nav",
            "hhi10_basis": "weights normalized within public top ten",
            "name_jaccard_basis": "exact disclosed stock names",
            "common_nav_share_basis": (
                "sum of pairwise minimum NAV weights by stock code"
            ),
            "comparison_period_rule": "same report period only",
            "terminology": "公开前十大持仓重合",
        },
        "inputs": {
            "nav_daily_sha256": nav_sha,
            "top10_holdings_sha256": top10_sha,
        },
        "nav_metrics": nav_metric_json,
        "return_correlation": correlation_json,
        "holding_metrics": holding_json,
        "public_top10_overlap": overlap_json,
    }
    metrics_path = args.metrics_json.resolve()
    write_json(metrics_path, metrics_payload)

    audit = build_audit(
        return_rows=return_rows,
        nav_metrics=nav_metric_json,
        correlations=correlation_json,
        holding_metrics=holding_json,
        overlaps=overlap_json,
    )
    write_json(args.audit_output.resolve(), audit)

    output_rows = {
        "nav_returns": len(return_rows),
        "nav_metrics": len(nav_metric_rows),
        "return_correlation": len(correlation_rows),
        "holding_metrics": len(holding_rows),
        "public_top10_overlap": len(overlap_rows),
    }
    run_manifest = {
        "stage": "F3_METRICS",
        "generated_at": generated_at,
        "status": audit["status"],
        "inputs": {
            "data/curated/nav_daily.csv": {
                "sha256": nav_sha,
                "rows": 1455,
            },
            "data/curated/top10_holdings.csv": {
                "sha256": top10_sha,
                "rows": 120,
            },
            "results/f2_audit.json": {
                "sha256": sha256_file(args.f2_audit.resolve()),
                "status": "PASS",
            },
        },
        "outputs": {
            str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): {
                "sha256": sha256_file(path),
                "rows": output_rows[name],
            }
            for name, path in output_paths.items()
        },
        "metrics_json": {
            "path": str(metrics_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ),
            "sha256": sha256_file(metrics_path),
        },
        "code": {
            "src/metrics.py": sha256_file(
                PROJECT_ROOT / "src" / "metrics.py"
            ),
            "scripts/calculate_metrics.py": sha256_file(
                Path(__file__).resolve()
            ),
        },
    }
    write_json(args.run_manifest.resolve(), run_manifest)

    print(
        f"F3 metrics {audit['status']}: "
        f"{len(nav_metric_rows)} NAV summaries, "
        f"{len(correlation_rows)} correlation cells, "
        f"{len(holding_rows)} holding summaries, "
        f"{len(overlap_rows)} same-period overlap rows"
    )
    if args.strict and audit["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
