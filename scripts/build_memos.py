"""Build and audit F6 template Memos and fixed refusal cases."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.memo import (  # noqa: E402
    MEMO_HEADINGS,
    MIN_EVIDENCE_COVERAGE,
    MIN_TOP_SCORE,
    REFUSAL_MESSAGE,
    SYSTEM_NAME,
    retrieve_and_build_memo,
)
from src.retrieval import sha256_text, validate_index  # noqa: E402


DEFAULT_CHUNKS = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
DEFAULT_INDEX = (
    PROJECT_ROOT / "data" / "processed" / "tfidf_index.json"
)
DEFAULT_F5_AUDIT = PROJECT_ROOT / "results" / "f5_audit.json"
DEFAULT_MEMOS = (
    PROJECT_ROOT / "data" / "processed" / "f6_memos.jsonl"
)
DEFAULT_CASE_AUDIT = PROJECT_ROOT / "results" / "f6_case_audit.csv"
DEFAULT_AUDIT = PROJECT_ROOT / "results" / "f6_audit.json"
DEFAULT_RUN_MANIFEST = (
    PROJECT_ROOT / "results" / "f6_run_manifest.json"
)

CASE_AUDIT_FIELDS = (
    "case_id",
    "query_hash",
    "fund_code_filter",
    "period_filter",
    "expected_status",
    "actual_status",
    "top_score",
    "evidence_coverage",
    "decision_reason_codes",
    "expected_physical_page",
    "expected_page_cited",
    "citation_count",
    "format_valid",
    "citation_support_valid",
    "scope_valid",
    "exact_refusal",
    "status",
)

SMOKE_CASES = (
    {
        "case_id": "answer_manager_new",
        "query": "报告期内基金投资策略和运作分析 人工智能 TMT",
        "fund_code": "003567",
        "period": "2026Q2",
        "expected_status": "ANSWERED",
        "expected_physical_page": 7,
    },
    {
        "case_id": "answer_industry_new",
        "query": "报告期末按行业分类的境内股票投资组合 制造业",
        "fund_code": "003834",
        "period": "2026Q2",
        "expected_status": "ANSWERED",
        "expected_physical_page": 9,
    },
    {
        "case_id": "answer_top10_old",
        "query": "前十名股票投资明细 股票代码 股票名称",
        "fund_code": "002980",
        "period": "2025Q4",
        "expected_status": "ANSWERED",
        "expected_physical_page": 11,
    },
    {
        "case_id": "refuse_weather",
        "query": "今天天气怎么样",
        "fund_code": "003567",
        "period": "2026Q2",
        "expected_status": "REFUSED",
        "expected_physical_page": None,
    },
    {
        "case_id": "refuse_private_address",
        "query": "基金经理的家庭住址是什么",
        "fund_code": "003567",
        "period": "2026Q2",
        "expected_status": "REFUSED",
        "expected_physical_page": None,
    },
    {
        "case_id": "refuse_future_prediction",
        "query": "2027年收益率预测是多少",
        "fund_code": "003567",
        "period": "2026Q2",
        "expected_status": "REFUSED",
        "expected_physical_page": None,
    },
    {
        "case_id": "refuse_undisclosed_trade",
        "query": "基金经理明天会买入哪只股票",
        "fund_code": "003567",
        "period": "2026Q2",
        "expected_status": "REFUSED",
        "expected_physical_page": None,
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)


def write_json(path: Path, payload: dict) -> None:
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


def write_jsonl(path: Path, rows: list[dict]) -> None:
    atomic_write_text(
        path,
        "".join(
            json.dumps(
                row,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
            for row in rows
        ),
    )


def write_csv(
    path: Path, fieldnames: tuple[str, ...], rows: list[dict]
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


def validate_f5_gate(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("stage") != "F5" or payload.get("status") != "PASS":
        raise ValueError("F5 must pass before F6")
    model = payload.get("model", {})
    if "idf_values" in model or "vectors" in model:
        raise ValueError("tracked F5 audit contains private index data")
    if path.stat().st_size >= 100_000:
        raise ValueError("tracked F5 audit is unexpectedly large")
    return payload


def markdown_has_fixed_sections(markdown: str) -> bool:
    positions = [markdown.find(heading) for heading in MEMO_HEADINGS]
    return (
        all(position >= 0 for position in positions)
        and positions == sorted(positions)
        and all(markdown.count(heading) == 1 for heading in MEMO_HEADINGS)
    )


def citation_support_valid(
    memo: dict, chunk_by_id: dict[str, dict]
) -> bool:
    if memo["status"] == "REFUSED":
        return (
            memo["citations"] == []
            and memo["fact_excerpts"] == []
        )
    if len(memo["citations"]) != len(memo["fact_excerpts"]):
        return False
    for excerpt in memo["fact_excerpts"]:
        chunk = chunk_by_id.get(excerpt["chunk_id"])
        if chunk is None:
            return False
        if excerpt["text_hash"] != chunk["text_hash"]:
            return False
        if excerpt["excerpt"] not in chunk["text"]:
            return False
        if sha256_text(excerpt["excerpt"]) != excerpt["excerpt_hash"]:
            return False
    return True


def run_cases(
    *, index: dict, chunks: list[dict]
) -> tuple[list[dict], list[dict]]:
    chunk_by_id = {
        str(chunk["chunk_id"]): chunk for chunk in chunks
    }
    private_rows = []
    audit_rows = []
    for case in SMOKE_CASES:
        memo = retrieve_and_build_memo(
            case["query"],
            index=index,
            chunks=chunks,
            fund_codes=[case["fund_code"]],
            periods=[case["period"]],
        )
        answered = memo["status"] == "ANSWERED"
        format_valid = (
            markdown_has_fixed_sections(memo["markdown"])
            if answered
            else memo["markdown"] == REFUSAL_MESSAGE
        )
        support_valid = citation_support_valid(memo, chunk_by_id)
        scope_valid = all(
            citation["fund_code"] == case["fund_code"]
            and citation["period"] == case["period"]
            for citation in memo["citations"]
        )
        expected_page = case["expected_physical_page"]
        expected_page_cited = (
            any(
                citation["physical_page"] == expected_page
                for citation in memo["citations"]
            )
            if expected_page is not None
            else memo["citations"] == []
        )
        exact_refusal = (
            memo["markdown"] == REFUSAL_MESSAGE
            and memo["citations"] == []
            and memo["fact_excerpts"] == []
        )
        case_pass = (
            memo["status"] == case["expected_status"]
            and format_valid
            and support_valid
            and scope_valid
            and expected_page_cited
            and (
                exact_refusal
                if case["expected_status"] == "REFUSED"
                else not exact_refusal
            )
            and "LLM RAG" not in memo["markdown"]
        )
        private_rows.append(
            {
                "case_id": case["case_id"],
                "query": case["query"],
                "memo": memo,
            }
        )
        audit_rows.append(
            {
                "case_id": case["case_id"],
                "query_hash": memo["query_hash"],
                "fund_code_filter": case["fund_code"],
                "period_filter": case["period"],
                "expected_status": case["expected_status"],
                "actual_status": memo["status"],
                "top_score": format(
                    memo["decision"]["top_score"], ".17g"
                ),
                "evidence_coverage": format(
                    memo["decision"]["evidence_coverage"], ".17g"
                ),
                "decision_reason_codes": "|".join(
                    memo["decision"]["reason_codes"]
                ),
                "expected_physical_page": (
                    "" if expected_page is None else expected_page
                ),
                "expected_page_cited": str(
                    expected_page_cited
                ).lower(),
                "citation_count": len(memo["citations"]),
                "format_valid": str(format_valid).lower(),
                "citation_support_valid": str(
                    support_valid
                ).lower(),
                "scope_valid": str(scope_valid).lower(),
                "exact_refusal": str(exact_refusal).lower(),
                "status": "PASS" if case_pass else "FAIL",
            }
        )
    return private_rows, audit_rows


def build_audit(case_rows: list[dict]) -> dict:
    answered = [
        row for row in case_rows if row["expected_status"] == "ANSWERED"
    ]
    refused = [
        row for row in case_rows if row["expected_status"] == "REFUSED"
    ]
    checks = {
        "f5_input_gate_passed_and_compact": True,
        "system_name_is_not_llm_rag": (
            SYSTEM_NAME
            == "可追溯文档检索与模板化投研 Memo 系统"
        ),
        "fixed_evidence_gate_is_recorded": (
            MIN_TOP_SCORE == 0.05
            and MIN_EVIDENCE_COVERAGE == 0.50
        ),
        "all_answerable_cases_use_four_fixed_sections": all(
            row["actual_status"] == "ANSWERED"
            and row["format_valid"] == "true"
            for row in answered
        ),
        "all_answerable_cases_cite_expected_physical_page": all(
            row["expected_page_cited"] == "true" for row in answered
        ),
        "all_fact_excerpts_have_chunk_support": all(
            row["citation_support_valid"] == "true"
            for row in answered
        ),
        "all_refusal_cases_use_exact_fixed_message": all(
            row["actual_status"] == "REFUSED"
            and row["exact_refusal"] == "true"
            for row in refused
        ),
        "all_outputs_respect_selected_fund_and_period": all(
            row["scope_valid"] == "true" for row in case_rows
        ),
        "all_seven_smoke_cases_pass": (
            len(case_rows) == 7
            and all(row["status"] == "PASS" for row in case_rows)
        ),
        "offline_no_external_model_or_api": True,
        "f7_evaluation_and_holdout_not_started": True,
        "tracked_audit_excludes_query_and_source_text": all(
            "query" not in row
            and "memo" not in row
            and "excerpt" not in row
            and "text" not in row
            for row in case_rows
        ),
    }
    return {
        "stage": "F6",
        "schema_version": "f6_template_memo_refusal_v1",
        "generated_at": utc_now(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "system_name": SYSTEM_NAME,
        "memo_headings": list(MEMO_HEADINGS),
        "refusal_message": REFUSAL_MESSAGE,
        "evidence_gate": {
            "minimum_top_cosine_score": MIN_TOP_SCORE,
            "minimum_query_ngram_coverage": MIN_EVIDENCE_COVERAGE,
            "decision_rule": (
                "both thresholds must pass using at most three cited cards"
            ),
        },
        "counts": {
            "smoke_cases": len(case_rows),
            "answerable_cases": len(answered),
            "refusal_cases": len(refused),
            "passed_cases": sum(
                row["status"] == "PASS" for row in case_rows
            ),
        },
        "checks": checks,
        "case_results": [
            {
                "case_id": row["case_id"],
                "query_hash": row["query_hash"],
                "fund_code_filter": row["fund_code_filter"],
                "period_filter": row["period_filter"],
                "expected_status": row["expected_status"],
                "actual_status": row["actual_status"],
                "top_score": float(row["top_score"]),
                "evidence_coverage": float(row["evidence_coverage"]),
                "decision_reason_codes": row[
                    "decision_reason_codes"
                ].split("|"),
                "expected_physical_page": (
                    None
                    if row["expected_physical_page"] == ""
                    else int(row["expected_physical_page"])
                ),
                "status": row["status"],
            }
            for row in case_rows
        ],
        "private_output": {
            "path": "data/processed/f6_memos.jsonl",
            "contains_queries_and_source_excerpts": True,
            "git_ignored": True,
        },
        "next_stage": "F7",
        "next_stage_authorized": False,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--f5-audit", type=Path, default=DEFAULT_F5_AUDIT)
    parser.add_argument("--memos-output", type=Path, default=DEFAULT_MEMOS)
    parser.add_argument(
        "--case-audit", type=Path, default=DEFAULT_CASE_AUDIT
    )
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=DEFAULT_RUN_MANIFEST,
    )
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    chunks_path = args.chunks.resolve()
    index_path = args.index.resolve()
    f5_audit_path = args.f5_audit.resolve()
    validate_f5_gate(f5_audit_path)
    chunks = read_jsonl(chunks_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    validate_index(index, chunks)

    private_rows, case_rows = run_cases(index=index, chunks=chunks)
    audit = build_audit(case_rows)
    memos_path = args.memos_output.resolve()
    case_audit_path = args.case_audit.resolve()
    audit_path = args.audit_output.resolve()
    write_jsonl(memos_path, private_rows)
    write_csv(case_audit_path, CASE_AUDIT_FIELDS, case_rows)
    write_json(audit_path, audit)

    run_manifest = {
        "stage": "F6",
        "generated_at": utc_now(),
        "status": audit["status"],
        "inputs": {
            "data/processed/chunks.jsonl": {
                "sha256": sha256_file(chunks_path),
                "rows": len(chunks),
                "git_ignored": True,
            },
            "data/processed/tfidf_index.json": {
                "sha256": sha256_file(index_path),
                "indexed_chunks": index["chunk_count"],
                "git_ignored": True,
            },
            "results/f5_audit.json": {
                "sha256": sha256_file(f5_audit_path),
                "status": "PASS",
            },
        },
        "private_outputs": {
            str(memos_path.relative_to(PROJECT_ROOT)).replace("\\", "/"): {
                "sha256": sha256_file(memos_path),
                "rows": len(private_rows),
                "contains_queries_and_source_excerpts": True,
                "git_ignored": True,
            }
        },
        "tracked_audits": {
            str(case_audit_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ): {
                "sha256": sha256_file(case_audit_path),
                "rows": len(case_rows),
                "contains_source_text": False,
            },
            str(audit_path.relative_to(PROJECT_ROOT)).replace("\\", "/"): {
                "sha256": sha256_file(audit_path),
                "contains_source_text": False,
            },
        },
        "code": {
            "src/memo.py": sha256_file(
                PROJECT_ROOT / "src" / "memo.py"
            ),
            "scripts/build_memos.py": sha256_file(
                Path(__file__).resolve()
            ),
            "scripts/create_memo.py": sha256_file(
                PROJECT_ROOT / "scripts" / "create_memo.py"
            ),
            "tests/test_memo.py": sha256_file(
                PROJECT_ROOT / "tests" / "test_memo.py"
            ),
        },
    }
    write_json(args.run_manifest.resolve(), run_manifest)

    print(
        f"F6 {audit['status']}: {len(case_rows)} smoke cases, "
        f"{len([r for r in case_rows if r['actual_status'] == 'ANSWERED'])} "
        "answered, "
        f"{len([r for r in case_rows if r['actual_status'] == 'REFUSED'])} "
        "refused"
    )
    if args.strict and audit["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
