"""Build deterministic synthetic data and a bounded public real sample."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.memo import extract_excerpt  # noqa: E402
from src.metrics import (  # noqa: E402
    annualized_volatility,
    calculate_simple_returns,
    common_nav_share,
    cumulative_change,
    hhi10,
    maximum_drawdown,
    name_jaccard,
    pearson_correlation,
)
from src.retrieval import build_index, sha256_text  # noqa: E402


SYNTHETIC_DIR = PROJECT_ROOT / "data" / "demo_synthetic"
REAL_SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_real"

PERIOD_ENDS = {
    "2025Q3": "2025-09-30",
    "2025Q4": "2025-12-31",
    "2026Q1": "2026-03-31",
    "2026Q2": "2026-06-30",
}

SYNTHETIC_FUNDS = (
    ("SYN001", "稳健成长合成基金"),
    ("SYN002", "科技创新合成基金"),
    ("SYN003", "绿色转型合成基金"),
)

SYNTHETIC_INDUSTRIES = (
    ("C", "合成制造业"),
    ("I", "合成信息技术业"),
    ("J", "合成金融业"),
    ("L", "合成商务服务业"),
    ("M", "合成研发服务业"),
)

MANAGER_EXCERPT_KEYWORDS = (
    "市场",
    "行业",
    "人工智能",
    "半导体",
    "新能源",
    "储能",
    "组合",
    "配置",
    "投资机会",
)

MANAGER_EXCERPT_EXCLUSIONS = (
    "公平交易",
    "异常交易",
    "反向交易",
    "任职日期",
    "离任日期",
    "持有人数",
    "资产净值预警",
    "投资组合报告",
)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    # Frozen public artifacts use CRLF so their byte hashes remain stable on
    # Windows and Linux checkouts alike.
    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(normalized)
    os.replace(temp_path, path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    atomic_write_text(
        path,
        "".join(
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for row in rows
        ),
    )


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(
        temp_path,
        index=False,
        encoding="utf-8",
        lineterminator="\r\n",
    )
    os.replace(temp_path, path)


def business_dates(start: date, count: int) -> list[date]:
    dates = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def nav_metric_rows(nav: pd.DataFrame) -> pd.DataFrame:
    rows = []
    input_hash = sha256_text(
        nav[["fund_code", "date", "cumulative_nav"]]
        .to_csv(index=False, lineterminator="\n")
    )
    for (fund_code, fund_name), group in nav.groupby(
        ["fund_code", "fund_name"],
        sort=True,
    ):
        ordered = group.sort_values("date")
        dates = [
            pd.Timestamp(item).date() for item in ordered["date"]
        ]
        values = ordered["cumulative_nav"].astype(float).tolist()
        returns = calculate_simple_returns(values)
        drawdown = maximum_drawdown(dates, values)
        rows.append(
            {
                "fund_code": fund_code,
                "fund_name": fund_name,
                "start_date": dates[0].isoformat(),
                "end_date": dates[-1].isoformat(),
                "nav_observations": len(values),
                "return_observations": len(returns),
                "cumulative_change": cumulative_change(values),
                "annualized_volatility": annualized_volatility(returns),
                "max_drawdown": drawdown["max_drawdown"],
                "drawdown_peak_date": drawdown[
                    "peak_date"
                ].isoformat(),
                "drawdown_trough_date": drawdown[
                    "trough_date"
                ].isoformat(),
                "drawdown_recovery_date": (
                    drawdown["recovery_date"].isoformat()
                    if drawdown["recovery_date"]
                    else ""
                ),
                "nav_field": "cumulative_nav",
                "trading_days_per_year": 252,
                "input_sha256": input_hash,
            }
        )
    return pd.DataFrame(rows)


def correlation_rows(nav: pd.DataFrame) -> pd.DataFrame:
    names = (
        nav[["fund_code", "fund_name"]]
        .drop_duplicates()
        .sort_values("fund_code")
    )
    values: dict[str, list[float]] = {}
    dates: list[str] | None = None
    for row in names.itertuples(index=False):
        ordered = nav.loc[
            nav["fund_code"] == row.fund_code
        ].sort_values("date")
        values[row.fund_code] = calculate_simple_returns(
            ordered["cumulative_nav"].astype(float).tolist()
        )
        current_dates = ordered["date"].astype(str).tolist()[1:]
        if dates is None:
            dates = current_dates
        elif dates != current_dates:
            raise ValueError("NAV sample is not on a common date window")
    assert dates is not None
    rows = []
    name_map = dict(
        zip(names["fund_code"].astype(str), names["fund_name"])
    )
    input_hash = sha256_text(
        nav[["fund_code", "date", "cumulative_nav"]]
        .to_csv(index=False, lineterminator="\n")
    )
    for left_code in name_map:
        for right_code in name_map:
            rows.append(
                {
                    "fund_code_a": left_code,
                    "fund_name_a": name_map[left_code],
                    "fund_code_b": right_code,
                    "fund_name_b": name_map[right_code],
                    "start_return_date": dates[0],
                    "end_return_date": dates[-1],
                    "paired_observations": len(dates),
                    "pearson_correlation": pearson_correlation(
                        values[left_code],
                        values[right_code],
                    ),
                    "input_sha256": input_hash,
                }
            )
    return pd.DataFrame(rows)


def synthetic_nav() -> pd.DataFrame:
    dates = business_dates(date(2026, 1, 5), 80)
    rows = []
    for fund_index, (fund_code, fund_name) in enumerate(
        SYNTHETIC_FUNDS
    ):
        nav = 1.0 + 0.04 * fund_index
        for day_index, current_date in enumerate(dates):
            if day_index:
                daily_return = (
                    0.00035
                    + 0.0045
                    * math.sin((day_index + 3 * fund_index) / 5.0)
                    + 0.0022
                    * math.cos((day_index + fund_index) / 11.0)
                )
                nav *= 1.0 + daily_return
            rows.append(
                {
                    "fund_code": fund_code,
                    "fund_name": fund_name,
                    "date": current_date.isoformat(),
                    "unit_nav": round(nav, 6),
                    "cumulative_nav": round(nav, 6),
                    "source_kind": "fully_synthetic",
                    "source_url": (
                        f"https://example.invalid/synthetic/{fund_code}"
                    ),
                }
            )
    return pd.DataFrame(rows)


def synthetic_holdings() -> tuple[pd.DataFrame, pd.DataFrame]:
    periods = list(PERIOD_ENDS)
    stock_names = [f"合成股票{index:02d}" for index in range(1, 21)]
    stock_codes = [f"S{index:05d}" for index in range(1, 21)]
    base_weights = [
        Decimal(item)
        for item in (
            "5.20",
            "4.60",
            "4.10",
            "3.80",
            "3.50",
            "3.20",
            "2.90",
            "2.60",
            "2.30",
            "2.00",
        )
    ]
    holding_rows = []
    metric_rows = []
    for fund_index, (fund_code, fund_name) in enumerate(
        SYNTHETIC_FUNDS
    ):
        for period_index, period in enumerate(periods):
            start = fund_index * 5 + period_index
            selected = [
                (start + offset) % len(stock_codes)
                for offset in range(10)
            ]
            adjustment = Decimal(period_index) * Decimal("0.03")
            weights = [
                weight + adjustment for weight in base_weights
            ]
            doc_id = f"{fund_code}_{period}"
            pdf_hash = sha256_text("synthetic:" + doc_id)
            for rank, (stock_index, weight) in enumerate(
                zip(selected, weights),
                start=1,
            ):
                holding_rows.append(
                    {
                        "doc_id": doc_id,
                        "fund_code": fund_code,
                        "fund_name": fund_name,
                        "period": period,
                        "period_end": PERIOD_ENDS[period],
                        "schema_version": "synthetic_v1",
                        "public_holding_rank": rank,
                        "stock_code": stock_codes[stock_index],
                        "stock_name": stock_names[stock_index],
                        "shares": 1000000 + 10000 * rank,
                        "fair_value_cny": 10000000 + 500000 * rank,
                        "nav_ratio_pct": float(weight),
                        "source_page": 2,
                        "announcement_url": (
                            "https://example.invalid/synthetic/"
                            f"{doc_id}"
                        ),
                        "file_url": "",
                        "source_pdf_sha256": pdf_hash,
                    }
                )
            ratio_weights = [weight / Decimal("100") for weight in weights]
            c10_value = sum(ratio_weights, Decimal("0"))
            metric_rows.append(
                {
                    "doc_id": doc_id,
                    "fund_code": fund_code,
                    "fund_name": fund_name,
                    "period": period,
                    "period_end": PERIOD_ENDS[period],
                    "disclosed_holding_count": 10,
                    "c10": float(c10_value),
                    "hhi10": float(hhi10(ratio_weights)),
                    "terminology": "公开前十大持仓",
                    "source_pdf_sha256": pdf_hash,
                    "input_sha256": sha256_text(
                        "synthetic_holdings_v1"
                    ),
                }
            )
    return pd.DataFrame(holding_rows), pd.DataFrame(metric_rows)


def overlap_from_holdings(holdings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period, period_frame in holdings.groupby("period", sort=True):
        funds = sorted(period_frame["fund_code"].unique().tolist())
        for left_index, left_code in enumerate(funds):
            for right_code in funds[left_index + 1 :]:
                left = period_frame.loc[
                    period_frame["fund_code"] == left_code
                ]
                right = period_frame.loc[
                    period_frame["fund_code"] == right_code
                ]
                left_names = left["stock_name"].astype(str).tolist()
                right_names = right["stock_name"].astype(str).tolist()
                left_weights = {
                    str(row.stock_code): Decimal(str(row.nav_ratio_pct))
                    / Decimal("100")
                    for row in left.itertuples(index=False)
                }
                right_weights = {
                    str(row.stock_code): Decimal(str(row.nav_ratio_pct))
                    / Decimal("100")
                    for row in right.itertuples(index=False)
                }
                common_codes = sorted(
                    set(left_weights) & set(right_weights)
                )
                left_name = str(left.iloc[0]["fund_name"])
                right_name = str(right.iloc[0]["fund_name"])
                left_doc = str(left.iloc[0]["doc_id"])
                right_doc = str(right.iloc[0]["doc_id"])
                rows.append(
                    {
                        "period": period,
                        "period_end": PERIOD_ENDS[period],
                        "fund_code_a": left_code,
                        "fund_name_a": left_name,
                        "fund_code_b": right_code,
                        "fund_name_b": right_name,
                        "common_stock_count": len(common_codes),
                        "name_intersection_count": len(
                            set(left_names) & set(right_names)
                        ),
                        "name_union_count": len(
                            set(left_names) | set(right_names)
                        ),
                        "name_jaccard": float(
                            name_jaccard(left_names, right_names)
                        ),
                        "common_nav_share": float(
                            common_nav_share(
                                left_weights,
                                right_weights,
                            )
                        ),
                        "common_stock_codes": "|".join(common_codes),
                        "doc_id_a": left_doc,
                        "doc_id_b": right_doc,
                        "source_pdf_sha256_a": str(
                            left.iloc[0]["source_pdf_sha256"]
                        ),
                        "source_pdf_sha256_b": str(
                            right.iloc[0]["source_pdf_sha256"]
                        ),
                        "terminology": "公开前十大持仓重合",
                        "input_sha256": sha256_text(
                            "synthetic_overlap_v1"
                        ),
                    }
                )
    return pd.DataFrame(rows)


def synthetic_industry() -> pd.DataFrame:
    rows = []
    periods = list(PERIOD_ENDS)
    for fund_index, (fund_code, fund_name) in enumerate(
        SYNTHETIC_FUNDS
    ):
        for period_index, period in enumerate(periods):
            doc_id = f"{fund_code}_{period}"
            values = [
                12.0 + 2.0 * fund_index - 0.4 * period_index,
                18.0 + 1.5 * fund_index + 0.8 * period_index,
                8.0 + 0.3 * period_index,
                6.0 + 0.5 * fund_index,
                10.0 + 0.6 * period_index,
            ]
            for (industry_code, industry_name), ratio in zip(
                SYNTHETIC_INDUSTRIES,
                values,
            ):
                rows.append(
                    {
                        "doc_id": doc_id,
                        "fund_code": fund_code,
                        "fund_name": fund_name,
                        "period": period,
                        "period_end": PERIOD_ENDS[period],
                        "schema_version": "synthetic_v1",
                        "industry_code": industry_code,
                        "industry_name": industry_name,
                        "fair_value_cny": round(ratio * 10000000, 2),
                        "nav_ratio_pct": round(ratio, 2),
                        "source_page": 3,
                        "announcement_url": (
                            "https://example.invalid/synthetic/"
                            f"{doc_id}"
                        ),
                        "file_url": "",
                        "source_pdf_sha256": sha256_text(
                            "synthetic:" + doc_id
                        ),
                    }
                )
    return pd.DataFrame(rows)


def synthetic_corpus(
    holding_metrics: pd.DataFrame,
    industry: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    manifests = []
    chunks = []
    for fund_code, fund_name in SYNTHETIC_FUNDS:
        for period in PERIOD_ENDS:
            doc_id = f"{fund_code}_{period}"
            pdf_hash = sha256_text("synthetic:" + doc_id)
            c10_value = float(
                holding_metrics.loc[
                    holding_metrics["doc_id"] == doc_id,
                    "c10",
                ].iloc[0]
            )
            top_industry = (
                industry.loc[industry["doc_id"] == doc_id]
                .sort_values("nav_ratio_pct", ascending=False)
                .iloc[0]
            )
            text = (
                f"{fund_name}在{period}合成报告中表示，本期市场保持震荡，"
                "组合采用分散配置并关注经营质量。"
                f"公开前十大持仓占净值比例为{c10_value:.2%}，"
                f"合成行业配置中{top_industry['industry_name']}占比较高。"
                "本段为完全合成的演示文本，不对应任何真实基金事实。"
            )
            text_hash = sha256_text(text)
            url = f"https://example.invalid/synthetic/{doc_id}"
            manifests.append(
                {
                    "doc_id": doc_id,
                    "fund_code": fund_code,
                    "fund_name": fund_name,
                    "period": period,
                    "period_end": PERIOD_ENDS[period],
                    "announcement_url": url,
                    "file_url": "",
                    "schema_version": "synthetic_v1",
                    "page_count": 1,
                    "sha256": pdf_hash,
                    "access_status": "synthetic",
                }
            )
            chunks.append(
                {
                    "chunk_id": f"{doc_id}_p001_c001",
                    "doc_id": doc_id,
                    "fund_code": fund_code,
                    "fund_name": fund_name,
                    "period": period,
                    "period_end": PERIOD_ENDS[period],
                    "page_number": 1,
                    "page_start": 1,
                    "page_end": 1,
                    "text": text,
                    "text_hash": text_hash,
                    "page_text_hash": text_hash,
                    "source_pdf_sha256": pdf_hash,
                    "announcement_url": url,
                    "file_url": "",
                    "sample_scope": "fully_synthetic",
                }
            )
    return pd.DataFrame(manifests), chunks


def build_synthetic() -> dict[str, int]:
    nav = synthetic_nav()
    holdings, holding_metrics = synthetic_holdings()
    overlap = overlap_from_holdings(holdings)
    industry = synthetic_industry()
    manifest, chunks = synthetic_corpus(holding_metrics, industry)
    index = build_index(chunks)

    frames = {
        "nav_daily.csv": nav,
        "nav_metrics.csv": nav_metric_rows(nav),
        "return_correlation.csv": correlation_rows(nav),
        "top10_holdings.csv": holdings,
        "holding_metrics.csv": holding_metrics,
        "public_top10_overlap.csv": overlap,
        "industry_allocation.csv": industry,
        "source_manifest.csv": manifest,
    }
    for filename, frame in frames.items():
        write_csv(SYNTHETIC_DIR / filename, frame)
    write_jsonl(SYNTHETIC_DIR / "chunks.jsonl", chunks)
    write_json(SYNTHETIC_DIR / "tfidf_index.json", index)
    counts = {
        "funds": int(nav["fund_code"].nunique()),
        "periods": int(holding_metrics["period"].nunique()),
        "reports": int(manifest["doc_id"].nunique()),
        "nav_rows": int(len(nav)),
        "holding_rows": int(len(holdings)),
        "industry_rows": int(len(industry)),
        "short_text_rows": int(len(chunks)),
    }
    write_json(
        SYNTHETIC_DIR / "profile.json",
        {
            "profile": "demo_synthetic",
            "dataset_version": "f9_synthetic_v1",
            "contains_real_fund_data": False,
            "contains_complete_pdf": False,
            "network_required": False,
            "api_key_required": False,
            "source_policy": "fully_synthetic_reserved_domain",
            "counts": counts,
        },
    )
    return counts


def read_local_csv(
    relative_path: str,
    *,
    code_columns: tuple[str, ...],
) -> pd.DataFrame:
    path = PROJECT_ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(
            f"local source required for real sample: {relative_path}"
        )
    frame = pd.read_csv(
        path,
        dtype={column: "string" for column in code_columns},
    )
    for column in code_columns:
        if column in frame:
            frame[column] = frame[column].astype(str).str.zfill(6)
    return frame


def select_manager_excerpt(candidates: list[dict]) -> str:
    segments: list[str] = []
    for candidate in candidates:
        segments.extend(
            segment.strip()
            for segment in re.split(
                r"(?<=[。！？；])|\n",
                str(candidate["text"]),
            )
            if segment.strip()
        )
    unique_segments = list(dict.fromkeys(segments))

    def score(segment: str) -> tuple[int, int, int]:
        if any(
            exclusion in segment
            for exclusion in MANAGER_EXCERPT_EXCLUSIONS
        ):
            return (-1, -1, -1)
        matched = sum(
            keyword in segment
            for keyword in MANAGER_EXCERPT_KEYWORDS
        )
        return (matched, min(len(segment), 110), -len(segment))

    source = max(unique_segments, key=score)
    matched_keywords = [
        keyword
        for keyword in MANAGER_EXCERPT_KEYWORDS
        if keyword in source
    ]
    if not matched_keywords:
        raise ValueError("manager-analysis excerpt has no research keyword")
    excerpt = extract_excerpt(
        "".join(matched_keywords),
        source,
        max_chars=110,
    )
    if any(
        exclusion in excerpt
        for exclusion in MANAGER_EXCERPT_EXCLUSIONS
    ):
        raise ValueError("manager-analysis excerpt contains excluded text")
    return excerpt


def build_real_sample() -> dict[str, int]:
    selected_periods = ("2026Q1", "2026Q2")
    nav_full = read_local_csv(
        "data/curated/nav_daily.csv",
        code_columns=("fund_code",),
    )
    common_dates = sorted(nav_full["date"].unique().tolist())[-20:]
    nav = (
        nav_full.loc[nav_full["date"].isin(common_dates)]
        [
            [
                "fund_code",
                "fund_name",
                "date",
                "unit_nav",
                "cumulative_nav",
                "source_kind",
                "source_url",
            ]
        ]
        .sort_values(["date", "fund_code"])
        .reset_index(drop=True)
    )
    holdings_full = read_local_csv(
        "data/curated/top10_holdings.csv",
        code_columns=("fund_code", "stock_code"),
    )
    holdings = holdings_full.loc[
        holdings_full["period"].isin(selected_periods)
    ].copy()
    holding_metrics_full = read_local_csv(
        "data/processed/holding_metrics.csv",
        code_columns=("fund_code",),
    )
    holding_metrics = holding_metrics_full.loc[
        holding_metrics_full["period"].isin(selected_periods)
    ].copy()
    overlap_full = read_local_csv(
        "data/processed/public_top10_overlap.csv",
        code_columns=("fund_code_a", "fund_code_b"),
    )
    overlap = overlap_full.loc[
        overlap_full["period"].isin(selected_periods)
    ].copy()

    industry_full = read_local_csv(
        "data/curated/industry_allocation.csv",
        code_columns=("fund_code",),
    )
    industry_selected = industry_full.loc[
        industry_full["period"].isin(selected_periods)
        & industry_full["nav_ratio_pct"].notna()
    ].copy()
    industry_selected["nav_ratio_pct"] = pd.to_numeric(
        industry_selected["nav_ratio_pct"],
        errors="raise",
    )
    industry = (
        industry_selected.sort_values(
            ["doc_id", "nav_ratio_pct"],
            ascending=[True, False],
        )
        .groupby("doc_id", sort=True)
        .head(5)
        .sort_values(["doc_id", "industry_code"])
        .reset_index(drop=True)
    )

    manifest_full = read_local_csv(
        "data/source_manifest.csv",
        code_columns=("fund_code",),
    )
    manifest = manifest_full.loc[
        manifest_full["period"].isin(selected_periods),
        [
            "doc_id",
            "fund_code",
            "fund_name",
            "period",
            "period_end",
            "announcement_url",
            "file_url",
            "schema_version",
            "page_count",
            "sha256",
            "access_status",
            "page_manager_analysis",
        ],
    ].copy()

    chunks_path = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
    local_chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    sample_chunks = []
    for row in manifest.sort_values("doc_id").itertuples(index=False):
        candidates = [
            chunk
            for chunk in local_chunks
            if chunk["doc_id"] == row.doc_id
            and int(chunk["page_number"])
            == int(row.page_manager_analysis)
        ]
        if not candidates:
            raise ValueError(
                f"{row.doc_id}: no manager-analysis chunk for sample"
            )
        sources = sorted(
            candidates,
            key=lambda item: item["chunk_id"],
        )
        source = sources[0]
        excerpt = select_manager_excerpt(sources)
        sample_chunks.append(
            {
                "chunk_id": f"sample_{row.doc_id}_p{int(row.page_manager_analysis):03d}",
                "doc_id": row.doc_id,
                "fund_code": row.fund_code,
                "fund_name": row.fund_name,
                "period": row.period,
                "period_end": row.period_end,
                "page_number": int(row.page_manager_analysis),
                "page_start": int(row.page_manager_analysis),
                "page_end": int(row.page_manager_analysis),
                "text": excerpt,
                "text_hash": sha256_text(excerpt),
                "page_text_hash": source["page_text_hash"],
                "source_pdf_sha256": row.sha256,
                "announcement_url": row.announcement_url,
                "file_url": row.file_url,
                "sample_scope": "bounded_real_excerpt_max_110_chars",
            }
        )
    manifest = manifest.drop(columns="page_manager_analysis")
    index = build_index(sample_chunks)

    frames = {
        "nav_daily.csv": nav,
        "nav_metrics.csv": nav_metric_rows(nav),
        "return_correlation.csv": correlation_rows(nav),
        "top10_holdings.csv": holdings,
        "holding_metrics.csv": holding_metrics,
        "public_top10_overlap.csv": overlap,
        "industry_allocation.csv": industry,
        "source_manifest.csv": manifest,
    }
    for filename, frame in frames.items():
        write_csv(REAL_SAMPLE_DIR / filename, frame)
    write_jsonl(REAL_SAMPLE_DIR / "chunks.jsonl", sample_chunks)
    write_json(REAL_SAMPLE_DIR / "tfidf_index.json", index)
    counts = {
        "funds": int(nav["fund_code"].nunique()),
        "periods": int(holding_metrics["period"].nunique()),
        "reports": int(manifest["doc_id"].nunique()),
        "nav_rows": int(len(nav)),
        "holding_rows": int(len(holdings)),
        "industry_rows": int(len(industry)),
        "short_text_rows": int(len(sample_chunks)),
        "maximum_excerpt_chars": max(
            len(item["text"]) for item in sample_chunks
        ),
    }
    write_json(
        REAL_SAMPLE_DIR / "profile.json",
        {
            "profile": "sample_real",
            "dataset_version": "f9_real_sample_v1",
            "contains_real_fund_data": True,
            "contains_complete_pdf": False,
            "network_required": False,
            "api_key_required": False,
            "source_policy": "official_manager_sources_only",
            "excerpt_limit_chars": 110,
            "counts": counts,
        },
    )
    return counts


def parse_args(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-real-sample",
        action="store_true",
        help=(
            "Maintainer-only: rebuild the bounded sample from ignored "
            "local research files."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    synthetic_counts = build_synthetic()
    print(
        "Synthetic demo built: "
        f"{synthetic_counts['funds']} funds, "
        f"{synthetic_counts['reports']} reports, "
        f"{synthetic_counts['nav_rows']} NAV rows"
    )
    if args.include_real_sample:
        real_counts = build_real_sample()
        print(
            "Bounded real sample built: "
            f"{real_counts['funds']} funds, "
            f"{real_counts['reports']} reports, "
            f"max excerpt {real_counts['maximum_excerpt_chars']} chars"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
