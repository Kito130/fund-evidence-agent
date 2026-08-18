"""Read-only data adapters for the local F8 Streamlit application."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.memo import MAX_MEMO_CARDS, build_memo
from src.retrieval import retrieve, validate_index


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PROFILE = "demo_synthetic"

PROFILE_LABELS = {
    "demo_synthetic": "合成演示（默认）",
    "sample_real": "小型真实样例",
    "local_full": "本地完整研究",
}

PAGE_LABELS = (
    "基金与组合诊断",
    "研究证据与 Memo",
)

F8_FEATURES = {
    "diagnostics": (
        "nav",
        "drawdown",
        "correlation",
        "c10",
        "hhi10",
        "public_top10_overlap",
        "industry_change",
        "disclosure_boundary",
    ),
    "research": (
        "fund_selection",
        "period_selection",
        "question_input",
        "top_k_evidence_cards",
        "document_and_pdf_page",
        "template_memo",
        "markdown_export",
        "evidence_refusal",
    ),
}

DATA_PATHS = {
    "nav": "data/curated/nav_daily.csv",
    "nav_metrics": "data/processed/nav_metrics.csv",
    "correlation": "data/processed/return_correlation.csv",
    "holding_metrics": "data/processed/holding_metrics.csv",
    "overlap": "data/processed/public_top10_overlap.csv",
    "industry": "data/curated/industry_allocation.csv",
    "manifest": "data/source_manifest.csv",
}

PUBLIC_DATA_FILENAMES = {
    "nav": "nav_daily.csv",
    "nav_metrics": "nav_metrics.csv",
    "correlation": "return_correlation.csv",
    "holding_metrics": "holding_metrics.csv",
    "overlap": "public_top10_overlap.csv",
    "industry": "industry_allocation.csv",
    "manifest": "source_manifest.csv",
}

PROFILE_DIRECTORIES = {
    "demo_synthetic": "data/demo_synthetic",
    "sample_real": "data/sample_real",
}

REQUIRED_COLUMNS = {
    "nav": {
        "fund_code",
        "fund_name",
        "date",
        "cumulative_nav",
    },
    "nav_metrics": {
        "fund_code",
        "fund_name",
        "cumulative_change",
        "annualized_volatility",
        "max_drawdown",
    },
    "correlation": {
        "fund_code_a",
        "fund_name_a",
        "fund_code_b",
        "fund_name_b",
        "pearson_correlation",
    },
    "holding_metrics": {
        "fund_code",
        "fund_name",
        "period",
        "c10",
        "hhi10",
    },
    "overlap": {
        "period",
        "fund_code_a",
        "fund_name_a",
        "fund_code_b",
        "fund_name_b",
        "common_stock_count",
        "name_jaccard",
        "common_nav_share",
    },
    "industry": {
        "fund_code",
        "fund_name",
        "period",
        "period_end",
        "industry_code",
        "industry_name",
        "nav_ratio_pct",
    },
    "manifest": {
        "doc_id",
        "fund_code",
        "fund_name",
        "period",
        "sha256",
    },
}


class F8GateError(ValueError):
    """Raised when F8 cannot safely read the frozen F1-F7 outputs."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_f7_gate(
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Require a passing, immutable F7 and an exactly-once holdout lock."""
    root = project_root.resolve()
    audit_path = root / "results" / "f7_audit.json"
    lock_path = root / "results" / "f7_holdout_lock.json"
    freeze_path = root / "results" / "f7_freeze_manifest.json"
    for path in (audit_path, lock_path, freeze_path):
        if not path.is_file():
            raise F8GateError(f"missing F7 gate file: {path.name}")

    audit = _read_json(audit_path)
    lock = _read_json(lock_path)
    freeze = _read_json(freeze_path)
    if audit.get("stage") != "F7" or audit.get("status") != "PASS":
        raise F8GateError("F7 audit must be PASS")
    if not all(audit.get("protocol_checks", {}).values()):
        raise F8GateError("F7 protocol checks must all pass")
    if not all(audit.get("performance_checks", {}).values()):
        raise F8GateError("F7 performance checks must all pass")
    if (
        lock.get("status") != "COMPLETED"
        or lock.get("run_count") != 1
        or lock.get("rerun_forbidden") is not True
    ):
        raise F8GateError("F7 holdout lock is not exactly-once")
    if freeze.get("status") != "FROZEN":
        raise F8GateError("F7 assets are not frozen")

    drifted = []
    for relative_path, expected_hash in freeze["asset_sha256"].items():
        asset_path = root / relative_path
        if (
            not asset_path.is_file()
            or sha256_file(asset_path) != expected_hash
        ):
            drifted.append(relative_path)
    if drifted:
        raise F8GateError(
            "F7 frozen asset drift: " + ", ".join(sorted(drifted))
        )

    return {
        "status": "PASS",
        "frozen_asset_count": len(freeze["asset_sha256"]),
        "holdout_run_count": lock["run_count"],
        "rerun_forbidden": lock["rerun_forbidden"],
        "development_end_to_end": audit["development_metrics"][
            "end_to_end_pass_count"
        ],
        "holdout_end_to_end": audit["holdout_metrics"][
            "end_to_end_pass_count"
        ],
    }


def _read_csv(path: Path, *, code_columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        dtype={column: "string" for column in code_columns},
    )
    for column in code_columns:
        if column in frame.columns:
            frame[column] = frame[column].astype(str).str.zfill(6)
    return frame


def load_dashboard_data(
    project_root: Path = PROJECT_ROOT,
    *,
    profile: str = "local_full",
) -> dict[str, pd.DataFrame]:
    """Load the audited local tables without modifying them."""
    root = project_root.resolve()
    if profile == "local_full":
        paths = {
            key: root / relative_path
            for key, relative_path in DATA_PATHS.items()
        }
    elif profile in PROFILE_DIRECTORIES:
        profile_dir = root / PROFILE_DIRECTORIES[profile]
        paths = {
            key: profile_dir / filename
            for key, filename in PUBLIC_DATA_FILENAMES.items()
        }
    else:
        raise ValueError(f"unknown data profile: {profile}")
    bundle = {
        "nav": _read_csv(
            paths["nav"],
            code_columns=("fund_code",),
        ),
        "nav_metrics": _read_csv(
            paths["nav_metrics"],
            code_columns=("fund_code",),
        ),
        "correlation": _read_csv(
            paths["correlation"],
            code_columns=("fund_code_a", "fund_code_b"),
        ),
        "holding_metrics": _read_csv(
            paths["holding_metrics"],
            code_columns=("fund_code",),
        ),
        "overlap": _read_csv(
            paths["overlap"],
            code_columns=("fund_code_a", "fund_code_b"),
        ),
        "industry": _read_csv(
            paths["industry"],
            code_columns=("fund_code",),
        ),
        "manifest": _read_csv(
            paths["manifest"],
            code_columns=("fund_code",),
        ),
    }
    validate_dashboard_data(bundle)
    return bundle


def validate_dashboard_data(
    bundle: dict[str, pd.DataFrame],
) -> dict[str, int]:
    if set(bundle) != set(DATA_PATHS):
        raise F8GateError("dashboard table inventory mismatch")
    for key, required in REQUIRED_COLUMNS.items():
        missing = required - set(bundle[key].columns)
        if missing:
            raise F8GateError(
                f"{key} missing columns: {sorted(missing)}"
            )

    nav = bundle["nav"]
    if nav.duplicated(["fund_code", "date"]).any():
        raise F8GateError("NAV dates must be unique within each fund")
    if nav["fund_code"].nunique() != 3:
        raise F8GateError("F8 diagnostics require exactly three funds")
    period_count = int(bundle["holding_metrics"]["period"].nunique())
    if period_count < 2:
        raise F8GateError("holding metrics require at least two periods")
    report_count = int(bundle["manifest"]["doc_id"].nunique())
    if report_count != 3 * period_count:
        raise F8GateError("report inventory is not fund-by-period complete")
    if len(bundle["overlap"]) != 3 * period_count:
        raise F8GateError("overlap inventory is not period complete")
    return {
        "fund_count": int(nav["fund_code"].nunique()),
        "nav_rows": int(len(nav)),
        "report_count": report_count,
        "period_count": period_count,
        "industry_rows": int(len(bundle["industry"])),
    }


def available_profiles(
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    root = project_root.resolve()
    profiles = []
    for profile in ("demo_synthetic", "sample_real"):
        profile_dir = root / PROFILE_DIRECTORIES[profile]
        required = [
            profile_dir / filename
            for filename in PUBLIC_DATA_FILENAMES.values()
        ] + [
            profile_dir / "chunks.jsonl",
            profile_dir / "tfidf_index.json",
            profile_dir / "profile.json",
        ]
        if all(path.is_file() for path in required):
            profiles.append(profile)
    if all((root / relative).is_file() for relative in DATA_PATHS.values()):
        local_engine = (
            root / "data" / "processed" / "tfidf_index.json"
        )
        local_chunks = root / "data" / "processed" / "chunks.jsonl"
        if local_engine.is_file() and local_chunks.is_file():
            profiles.append("local_full")
    return profiles


def profile_metadata(
    profile: str,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    if profile == "local_full":
        return {
            "profile": profile,
            "dataset_version": "local_f1_f8_audited",
            "contains_real_fund_data": True,
            "contains_complete_pdf": True,
            "network_required": False,
            "api_key_required": False,
        }
    if profile not in PROFILE_DIRECTORIES:
        raise ValueError(f"unknown data profile: {profile}")
    path = (
        project_root.resolve()
        / PROFILE_DIRECTORIES[profile]
        / "profile.json"
    )
    return _read_json(path)


def public_evaluation_summary(
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    audit_path = (
        project_root.resolve() / "results" / "f7_audit.json"
    )
    if not audit_path.is_file():
        return {
            "status": "NOT_BUNDLED",
            "development_end_to_end": None,
            "holdout_end_to_end": None,
            "holdout_run_count": None,
            "rerun_forbidden": True,
        }
    audit = _read_json(audit_path)
    return {
        "status": audit.get("status", "UNKNOWN"),
        "development_end_to_end": audit.get(
            "development_metrics",
            {},
        ).get("end_to_end_pass_count"),
        "holdout_end_to_end": audit.get(
            "holdout_metrics",
            {},
        ).get("end_to_end_pass_count"),
        "holdout_run_count": audit.get(
            "holdout_execution",
            {},
        ).get("run_count"),
        "rerun_forbidden": audit.get(
            "holdout_execution",
            {},
        ).get("rerun_forbidden", True),
    }


def fund_labels(bundle: dict[str, pd.DataFrame]) -> dict[str, str]:
    rows = (
        bundle["nav"][["fund_code", "fund_name"]]
        .drop_duplicates()
        .sort_values("fund_code")
    )
    return {
        str(row.fund_code): f"{row.fund_code}｜{row.fund_name}"
        for row in rows.itertuples(index=False)
    }


def available_periods(bundle: dict[str, pd.DataFrame]) -> list[str]:
    return sorted(bundle["holding_metrics"]["period"].unique().tolist())


def nav_chart_frame(nav: pd.DataFrame) -> pd.DataFrame:
    frame = nav[["date", "fund_name", "cumulative_nav"]].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["cumulative_nav"] = pd.to_numeric(
        frame["cumulative_nav"],
        errors="raise",
    )
    chart = (
        frame.pivot(
            index="date",
            columns="fund_name",
            values="cumulative_nav",
        )
        .sort_index()
        .sort_index(axis=1)
    )
    if chart.isna().any().any():
        raise F8GateError("NAV chart is not on the frozen common window")
    chart.index.name = "日期"
    return chart


def drawdown_chart_frame(nav: pd.DataFrame) -> pd.DataFrame:
    values = nav_chart_frame(nav)
    drawdown = values.divide(values.cummax()).subtract(1.0).multiply(100)
    drawdown.index.name = "日期"
    return drawdown


def nav_metric_snapshot(nav_metrics: pd.DataFrame) -> pd.DataFrame:
    frame = nav_metrics[
        [
            "fund_code",
            "fund_name",
            "cumulative_change",
            "annualized_volatility",
            "max_drawdown",
            "drawdown_peak_date",
            "drawdown_trough_date",
        ]
    ].copy()
    for column in (
        "cumulative_change",
        "annualized_volatility",
        "max_drawdown",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise") * 100
    return frame.rename(
        columns={
            "fund_code": "基金代码",
            "fund_name": "基金名称",
            "cumulative_change": "区间累计变化(%)",
            "annualized_volatility": "年化波动率(%)",
            "max_drawdown": "最大回撤(%)",
            "drawdown_peak_date": "峰值日期",
            "drawdown_trough_date": "谷值日期",
        }
    ).sort_values("基金代码")


def correlation_matrix(correlation: pd.DataFrame) -> pd.DataFrame:
    frame = correlation.copy()
    frame["pearson_correlation"] = pd.to_numeric(
        frame["pearson_correlation"],
        errors="raise",
    )
    matrix = frame.pivot(
        index="fund_name_a",
        columns="fund_name_b",
        values="pearson_correlation",
    )
    names = sorted(
        set(frame["fund_name_a"]) | set(frame["fund_name_b"])
    )
    matrix = matrix.reindex(index=names, columns=names)
    if matrix.isna().any().any():
        raise F8GateError("correlation matrix is incomplete")
    matrix.index.name = "基金"
    matrix.columns.name = None
    return matrix


def holding_snapshot(
    holding_metrics: pd.DataFrame,
    period: str,
) -> pd.DataFrame:
    frame = holding_metrics.loc[
        holding_metrics["period"] == period,
        ["fund_code", "fund_name", "c10", "hhi10"],
    ].copy()
    if len(frame) != 3:
        raise F8GateError(f"{period}: holding metrics are incomplete")
    frame["c10"] = pd.to_numeric(frame["c10"], errors="raise") * 100
    frame["hhi10"] = pd.to_numeric(frame["hhi10"], errors="raise")
    return frame.rename(
        columns={
            "fund_code": "基金代码",
            "fund_name": "基金名称",
            "c10": "C10 (%)",
            "hhi10": "HHI10",
        }
    ).sort_values("基金代码")


def overlap_snapshot(
    overlap: pd.DataFrame,
    period: str,
) -> pd.DataFrame:
    frame = overlap.loc[overlap["period"] == period].copy()
    if len(frame) != 3:
        raise F8GateError(f"{period}: overlap pairs are incomplete")
    frame["基金组合"] = (
        frame["fund_name_a"].astype(str)
        + " × "
        + frame["fund_name_b"].astype(str)
    )
    frame["NameJaccard (%)"] = (
        pd.to_numeric(frame["name_jaccard"], errors="raise") * 100
    )
    frame["CommonNAVShare (%)"] = (
        pd.to_numeric(frame["common_nav_share"], errors="raise") * 100
    )
    frame["共同股票数"] = pd.to_numeric(
        frame["common_stock_count"],
        errors="raise",
    ).astype(int)
    return frame[
        [
            "基金组合",
            "共同股票数",
            "NameJaccard (%)",
            "CommonNAVShare (%)",
        ]
    ].sort_values("基金组合")


def industry_change_snapshot(
    industry: pd.DataFrame,
    *,
    fund_code: str,
    current_period: str,
) -> dict[str, Any]:
    frame = industry.loc[industry["fund_code"] == fund_code].copy()
    period_order = (
        frame[["period", "period_end"]]
        .drop_duplicates()
        .sort_values("period_end")["period"]
        .tolist()
    )
    if current_period not in period_order:
        raise ValueError(f"unknown report period: {current_period}")
    current_index = period_order.index(current_period)
    if current_index == 0:
        raise ValueError("industry change needs an earlier report period")
    previous_period = period_order[current_index - 1]

    previous = frame.loc[
        frame["period"] == previous_period,
        ["industry_code", "industry_name", "nav_ratio_pct"],
    ].rename(
        columns={
            "industry_name": "上期行业",
            "nav_ratio_pct": "上期(%)",
        }
    )
    current = frame.loc[
        frame["period"] == current_period,
        ["industry_code", "industry_name", "nav_ratio_pct"],
    ].rename(
        columns={
            "industry_name": "本期行业",
            "nav_ratio_pct": "本期(%)",
        }
    )
    merged = previous.merge(
        current,
        on="industry_code",
        how="outer",
        validate="one_to_one",
    )
    merged["行业"] = merged["本期行业"].fillna(merged["上期行业"])
    merged["上期(%)"] = pd.to_numeric(
        merged["上期(%)"],
        errors="coerce",
    )
    merged["本期(%)"] = pd.to_numeric(
        merged["本期(%)"],
        errors="coerce",
    )
    both = merged["上期(%)"].notna() & merged["本期(%)"].notna()
    new = merged["上期(%)"].isna() & merged["本期(%)"].notna()
    exited = merged["上期(%)"].notna() & merged["本期(%)"].isna()
    merged["变化(百分点)"] = (
        merged["本期(%)"] - merged["上期(%)"]
    ).where(both)
    merged["披露状态"] = "报告表均为空白"
    merged.loc[both, "披露状态"] = "连续披露"
    merged.loc[new, "披露状态"] = "本期新增披露"
    merged.loc[exited, "披露状态"] = "本期不再列示"
    merged["_sort"] = (
        merged["变化(百分点)"]
        .abs()
        .fillna(merged[["上期(%)", "本期(%)"]].max(axis=1))
        .fillna(-1)
    )
    result = (
        merged.loc[
            merged["上期(%)"].notna() | merged["本期(%)"].notna(),
            [
                "行业",
                "上期(%)",
                "本期(%)",
                "变化(百分点)",
                "披露状态",
                "_sort",
            ],
        ]
        .sort_values(["_sort", "行业"], ascending=[False, True])
        .drop(columns="_sort")
        .reset_index(drop=True)
    )
    return {
        "previous_period": previous_period,
        "current_period": current_period,
        "table": result,
    }


def load_research_engine(
    project_root: Path = PROJECT_ROOT,
    *,
    profile: str = "local_full",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = project_root.resolve()
    if profile == "local_full":
        engine_dir = root / "data" / "processed"
    elif profile in PROFILE_DIRECTORIES:
        engine_dir = root / PROFILE_DIRECTORIES[profile]
    else:
        raise ValueError(f"unknown data profile: {profile}")
    chunks_path = engine_dir / "chunks.jsonl"
    index_path = engine_dir / "tfidf_index.json"
    chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    index = _read_json(index_path)
    validate_index(index, chunks)
    return index, chunks


def research_scope(
    chunks: list[dict[str, Any]],
) -> tuple[dict[str, str], list[str]]:
    funds = {
        str(chunk["fund_code"]): str(chunk["fund_name"])
        for chunk in chunks
    }
    periods = sorted({str(chunk["period"]) for chunk in chunks})
    return dict(sorted(funds.items())), periods


def run_research_query(
    query: str,
    *,
    fund_code: str,
    period: str,
    top_k: int,
    index: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("问题不能为空")
    if not 1 <= top_k <= MAX_MEMO_CARDS:
        raise ValueError(
            f"top_k must be between 1 and {MAX_MEMO_CARDS}"
        )
    funds, periods = research_scope(chunks)
    if fund_code not in funds:
        raise ValueError(f"unknown fund: {fund_code}")
    if period not in periods:
        raise ValueError(f"unknown period: {period}")

    cards = retrieve(
        clean_query,
        index=index,
        chunks=chunks,
        fund_codes=[fund_code],
        periods=[period],
        top_k=top_k,
    )
    memo = build_memo(
        clean_query,
        cards=cards,
        fund_codes=[fund_code],
        periods=[period],
    )
    return {
        "fund_code": fund_code,
        "period": period,
        "top_k": top_k,
        "cards": cards,
        "memo": memo,
    }
