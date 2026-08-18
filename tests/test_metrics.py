from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import unittest
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.metrics import (
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


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MetricUnitTests(unittest.TestCase):
    def test_returns_do_not_fill_missing_calendar_dates(self):
        values = [1.0, 1.1, 1.21]
        observed_dates = [
            date(2026, 1, 2),
            date(2026, 1, 5),
            date(2026, 1, 9),
        ]
        returns = calculate_simple_returns(values)
        self.assertEqual(len(returns), len(observed_dates) - 1)
        self.assertAlmostEqual(returns[0], 0.1)
        self.assertAlmostEqual(returns[1], 0.1)

    def test_cumulative_change_is_end_over_start_minus_one(self):
        self.assertAlmostEqual(cumulative_change([2.0, 2.5, 3.0]), 0.5)

    def test_annualized_volatility_uses_sample_standard_deviation(self):
        returns = [0.01, -0.02, 0.03, 0.0]
        expected = statistics.stdev(returns) * math.sqrt(252)
        self.assertAlmostEqual(
            annualized_volatility(returns), expected, places=15
        )

    def test_maximum_drawdown_tracks_peak_and_trough(self):
        dates = [date(2026, 1, day) for day in range(1, 6)]
        result = maximum_drawdown(dates, [1.0, 1.2, 0.9, 1.0, 1.3])
        self.assertAlmostEqual(result["max_drawdown"], -0.25)
        self.assertEqual(result["peak_date"], date(2026, 1, 2))
        self.assertEqual(result["trough_date"], date(2026, 1, 3))
        self.assertEqual(result["recovery_date"], date(2026, 1, 5))

    def test_correlation_matches_perfect_linear_series(self):
        self.assertAlmostEqual(
            pearson_correlation([1, 2, 3], [2, 4, 6]), 1.0
        )
        self.assertAlmostEqual(
            pearson_correlation([1, 2, 3], [6, 4, 2]), -1.0
        )

    def test_c10_and_hhi10_match_equal_weight_hand_calculation(self):
        weights = [Decimal("0.01")] * 10
        self.assertEqual(c10(weights), Decimal("0.10"))
        self.assertEqual(hhi10(weights), Decimal("0.10"))

    def test_name_jaccard_matches_hand_calculation(self):
        self.assertEqual(
            name_jaccard({"A", "B"}, {"B", "C"}),
            Decimal(1) / Decimal(3),
        )

    def test_common_nav_share_matches_hand_calculation(self):
        left = {"A": Decimal("0.05"), "B": Decimal("0.03")}
        right = {"A": Decimal("0.02"), "C": Decimal("0.04")}
        self.assertEqual(common_nav_share(left, right), Decimal("0.02"))

    def test_public_top10_comparison_rejects_cross_period_inputs(self):
        validate_same_period("2026Q2", "2026Q2")
        with self.assertRaises(ValueError):
            validate_same_period("2026Q1", "2026Q2")


@unittest.skipUnless(
    PROCESSED.is_dir(),
    "private V1 processed metrics are not distributed in the public repository",
)
class MetricIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.returns = read_csv(PROCESSED / "nav_returns.csv")
        cls.nav_metrics = read_csv(PROCESSED / "nav_metrics.csv")
        cls.correlations = read_csv(
            PROCESSED / "return_correlation.csv"
        )
        cls.holdings = read_csv(PROCESSED / "holding_metrics.csv")
        cls.overlaps = read_csv(
            PROCESSED / "public_top10_overlap.csv"
        )
        cls.metrics_json = json.loads(
            (RESULTS / "metrics.json").read_text(encoding="utf-8")
        )

    def test_return_rows_are_unique_and_484_per_fund(self):
        keys = [(row["fund_code"], row["date"]) for row in self.returns]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(
            Counter(row["fund_code"] for row in self.returns),
            Counter({"003567": 484, "003834": 484, "002980": 484}),
        )

    def test_nav_metric_output_has_three_finite_rows(self):
        self.assertEqual(len(self.nav_metrics), 3)
        for row in self.nav_metrics:
            self.assertEqual(int(row["nav_observations"]), 485)
            self.assertEqual(int(row["return_observations"]), 484)
            for field in (
                "cumulative_change",
                "annualized_volatility",
                "max_drawdown",
            ):
                self.assertTrue(math.isfinite(float(row[field])))
            self.assertLessEqual(float(row["max_drawdown"]), 0)

    def test_correlation_matrix_is_symmetric_with_unit_diagonal(self):
        self.assertEqual(len(self.correlations), 9)
        values = {
            (row["fund_code_a"], row["fund_code_b"]): float(
                row["pearson_correlation"]
            )
            for row in self.correlations
        }
        for left in {"002980", "003567", "003834"}:
            self.assertAlmostEqual(values[(left, left)], 1.0, places=12)
            for right in {"002980", "003567", "003834"}:
                self.assertAlmostEqual(
                    values[(left, right)],
                    values[(right, left)],
                    places=12,
                )

    def test_holding_metrics_are_complete_and_in_range(self):
        self.assertEqual(len(self.holdings), 12)
        for row in self.holdings:
            self.assertEqual(int(row["disclosed_holding_count"]), 10)
            self.assertGreater(float(row["c10"]), 0)
            self.assertLessEqual(float(row["c10"]), 1)
            self.assertGreaterEqual(float(row["hhi10"]), 0.1)
            self.assertLessEqual(float(row["hhi10"]), 1)
            self.assertEqual(row["terminology"], "公开前十大持仓")

    def test_overlap_metrics_are_same_period_only(self):
        self.assertEqual(len(self.overlaps), 12)
        for row in self.overlaps:
            self.assertTrue(row["doc_id_a"].endswith(row["period"]))
            self.assertTrue(row["doc_id_b"].endswith(row["period"]))
            self.assertEqual(row["terminology"], "公开前十大持仓重合")
            self.assertGreaterEqual(float(row["name_jaccard"]), 0)
            self.assertLessEqual(float(row["name_jaccard"]), 1)
            self.assertGreaterEqual(float(row["common_nav_share"]), 0)
            self.assertLessEqual(float(row["common_nav_share"]), 1)

    def test_2026q2_representative_holding_values(self):
        holding = next(
            row
            for row in self.holdings
            if row["fund_code"] == "003567"
            and row["period"] == "2026Q2"
        )
        weights = [
            Decimal(value)
            for value in (
                "0.0490",
                "0.0392",
                "0.0377",
                "0.0305",
                "0.0299",
                "0.0273",
                "0.0260",
                "0.0243",
                "0.0228",
                "0.0213",
            )
        ]
        expected_c10 = sum(weights, Decimal("0"))
        expected_hhi = sum(
            (weight / expected_c10) ** 2 for weight in weights
        )
        self.assertAlmostEqual(float(holding["c10"]), float(expected_c10))
        self.assertAlmostEqual(float(holding["hhi10"]), float(expected_hhi))

    def test_2026q2_representative_overlap_values(self):
        overlap = next(
            row
            for row in self.overlaps
            if row["fund_code_a"] == "003567"
            and row["fund_code_b"] == "003834"
            and row["period"] == "2026Q2"
        )
        self.assertEqual(int(overlap["common_stock_count"]), 1)
        self.assertAlmostEqual(
            float(overlap["name_jaccard"]), 1 / 19, places=15
        )
        self.assertAlmostEqual(
            float(overlap["common_nav_share"]), 0.0299, places=15
        )

    def test_manual_formula_checks_all_pass(self):
        checks = read_csv(RESULTS / "f3_manual_checks.csv")
        self.assertEqual(len(checks), 14)
        self.assertTrue(all(row["status"] == "PASS" for row in checks))
        self.assertTrue(
            {"c10", "hhi10", "common_nav_share"}
            <= {row["check_id"] for row in checks}
        )

    def test_f3_audits_pass(self):
        for name in ("f3_metrics_audit.json", "f3_audit.json"):
            audit = json.loads(
                (RESULTS / name).read_text(encoding="utf-8")
            )
            self.assertEqual(audit["status"], "PASS")
            if "checks" in audit:
                self.assertTrue(all(audit["checks"].values()))

    def test_run_manifest_hashes_match_outputs(self):
        manifest = json.loads(
            (RESULTS / "f3_run_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "PASS")
        for relative_path, metadata in manifest["outputs"].items():
            self.assertEqual(
                sha256_file(ROOT / relative_path), metadata["sha256"]
            )
        self.assertEqual(
            sha256_file(RESULTS / "f3_manual_checks.csv"),
            manifest["manual_verification"]["checks_csv"]["sha256"],
        )

    def test_metrics_json_records_required_conventions(self):
        conventions = self.metrics_json["conventions"]
        self.assertEqual(conventions["annualization_factor"], 252)
        self.assertEqual(conventions["volatility_ddof"], 1)
        self.assertFalse(conventions["calendar_fill"])
        self.assertEqual(
            conventions["comparison_period_rule"],
            "same report period only",
        )
        self.assertEqual(
            conventions["terminology"], "公开前十大持仓重合"
        )


if __name__ == "__main__":
    unittest.main()
