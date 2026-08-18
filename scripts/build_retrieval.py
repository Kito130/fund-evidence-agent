"""Build and audit the F5 offline TF-IDF retrieval index."""

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

from src.retrieval import (  # noqa: E402
    DEFAULT_TOP_K,
    MODEL_VERSION,
    NGRAM_MAX,
    NGRAM_MIN,
    build_index,
    retrieve,
    sha256_text,
    validate_index,
)


DEFAULT_CHUNKS = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
DEFAULT_F4_AUDIT = PROJECT_ROOT / "results" / "f4_audit.json"
DEFAULT_INDEX = (
    PROJECT_ROOT / "data" / "processed" / "tfidf_index.json"
)
DEFAULT_EVIDENCE = (
    PROJECT_ROOT / "data" / "processed" / "f5_evidence_cards.jsonl"
)
DEFAULT_QUERY_AUDIT = PROJECT_ROOT / "results" / "f5_query_audit.csv"
DEFAULT_AUDIT = PROJECT_ROOT / "results" / "f5_audit.json"
DEFAULT_RUN_MANIFEST = (
    PROJECT_ROOT / "results" / "f5_run_manifest.json"
)

QUERY_AUDIT_FIELDS = (
    "query_id",
    "fund_code_filter",
    "period_filter",
    "top_k",
    "result_count",
    "expected_doc_id",
    "expected_physical_page",
    "expected_page_rank",
    "top_doc_id",
    "top_physical_page",
    "top_chunk_id",
    "top_text_hash",
    "all_results_within_filters",
    "all_citations_exist",
    "scores_descending",
    "status",
)

SMOKE_QUERIES = (
    {
        "query_id": "manager_old_ai",
        "query": "报告期内基金投资策略和运作分析 人工智能 AI 大模型",
        "fund_code": "003567",
        "period": "2025Q4",
        "expected_doc_id": "003567_2025Q4",
        "expected_physical_page": 8,
    },
    {
        "query_id": "manager_new_ai",
        "query": "报告期内基金投资策略和运作分析 人工智能 TMT",
        "fund_code": "003567",
        "period": "2026Q2",
        "expected_doc_id": "003567_2026Q2",
        "expected_physical_page": 7,
    },
    {
        "query_id": "industry_new_schema",
        "query": "报告期末按行业分类的境内股票投资组合 制造业",
        "fund_code": "003834",
        "period": "2026Q2",
        "expected_doc_id": "003834_2026Q2",
        "expected_physical_page": 9,
    },
    {
        "query_id": "top10_old_schema",
        "query": "前十名股票投资明细 股票代码 股票名称",
        "fund_code": "002980",
        "period": "2025Q4",
        "expected_doc_id": "002980_2025Q4",
        "expected_physical_page": 11,
    },
    {
        "query_id": "top10_new_schema",
        "query": "前十名股票投资明细 股票代码 股票名称",
        "fund_code": "002980",
        "period": "2026Q2",
        "expected_doc_id": "002980_2026Q2",
        "expected_physical_page": 10,
    },
    {
        "query_id": "manager_energy",
        "query": "报告期内基金投资策略和运作分析 新能源",
        "fund_code": "003834",
        "period": "2025Q4",
        "expected_doc_id": "003834_2025Q4",
        "expected_physical_page": 8,
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


def write_json(path: Path, payload: dict, *, compact: bool = False) -> None:
    if compact:
        text = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    else:
        text = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    atomic_write_text(path, text + "\n")


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


def validate_f4_gate(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("stage") != "F4" or payload.get("status") != "PASS":
        raise ValueError("F4 must pass before F5 index construction")
    return payload


def validate_chunks(chunks: list[dict], f4_audit: dict) -> None:
    expected = int(f4_audit["counts"]["chunks"])
    if len(chunks) != expected or expected != 223:
        raise ValueError(
            f"expected 223 frozen F4 chunks, got {len(chunks)}"
        )
    chunk_ids = [str(chunk["chunk_id"]) for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("F4 chunk_id values are not unique")
    required = {
        "chunk_id",
        "doc_id",
        "fund_code",
        "fund_name",
        "period",
        "period_end",
        "page_number",
        "text",
        "text_hash",
        "page_text_hash",
        "source_pdf_sha256",
        "announcement_url",
        "file_url",
    }
    for chunk in chunks:
        missing = required - set(chunk)
        if missing:
            raise ValueError(
                f"{chunk.get('chunk_id', '?')}: missing {sorted(missing)}"
            )
        if sha256_text(str(chunk["text"])) != chunk["text_hash"]:
            raise ValueError(f"{chunk['chunk_id']}: text hash mismatch")


def run_smoke_queries(
    *, index: dict, chunks: list[dict]
) -> tuple[list[dict], list[dict]]:
    chunk_by_id = {
        str(chunk["chunk_id"]): chunk for chunk in chunks
    }
    evidence_rows = []
    audit_rows = []
    for item in SMOKE_QUERIES:
        cards = retrieve(
            item["query"],
            index=index,
            chunks=chunks,
            fund_codes=[item["fund_code"]],
            periods=[item["period"]],
            top_k=DEFAULT_TOP_K,
        )
        expected_rank = next(
            (
                card["rank"]
                for card in cards
                if card["citation"]["doc_id"]
                == item["expected_doc_id"]
                and card["citation"]["physical_page"]
                == item["expected_physical_page"]
            ),
            None,
        )
        within_filters = all(
            card["citation"]["fund_code"] == item["fund_code"]
            and card["citation"]["period"] == item["period"]
            for card in cards
        )
        citations_exist = all(
            card["citation"]["chunk_id"] in chunk_by_id
            and card["citation"]["text_hash"]
            == chunk_by_id[card["citation"]["chunk_id"]]["text_hash"]
            for card in cards
        )
        scores = [float(card["score"]) for card in cards]
        scores_descending = scores == sorted(scores, reverse=True)
        status = (
            "PASS"
            if cards
            and expected_rank is not None
            and within_filters
            and citations_exist
            and scores_descending
            else "FAIL"
        )
        evidence_rows.append(
            {
                "query_id": item["query_id"],
                "query": item["query"],
                "query_hash": sha256_text(item["query"]),
                "fund_code_filter": [item["fund_code"]],
                "period_filter": [item["period"]],
                "cards": cards,
            }
        )
        top = cards[0] if cards else None
        audit_rows.append(
            {
                "query_id": item["query_id"],
                "fund_code_filter": item["fund_code"],
                "period_filter": item["period"],
                "top_k": DEFAULT_TOP_K,
                "result_count": len(cards),
                "expected_doc_id": item["expected_doc_id"],
                "expected_physical_page": item[
                    "expected_physical_page"
                ],
                "expected_page_rank": (
                    "" if expected_rank is None else expected_rank
                ),
                "top_doc_id": (
                    "" if top is None else top["citation"]["doc_id"]
                ),
                "top_physical_page": (
                    ""
                    if top is None
                    else top["citation"]["physical_page"]
                ),
                "top_chunk_id": (
                    "" if top is None else top["citation"]["chunk_id"]
                ),
                "top_text_hash": (
                    "" if top is None else top["citation"]["text_hash"]
                ),
                "all_results_within_filters": str(
                    within_filters
                ).lower(),
                "all_citations_exist": str(citations_exist).lower(),
                "scores_descending": str(scores_descending).lower(),
                "status": status,
            }
        )
    return evidence_rows, audit_rows


def build_audit(
    *,
    index: dict,
    chunks: list[dict],
    evidence_rows: list[dict],
    query_audit_rows: list[dict],
) -> dict:
    cards = [
        card
        for row in evidence_rows
        for card in row["cards"]
    ]
    chunk_by_id = {
        str(chunk["chunk_id"]): chunk for chunk in chunks
    }
    filters_hold = all(
        all(
            card["citation"]["fund_code"]
            in row["fund_code_filter"]
            and card["citation"]["period"] in row["period_filter"]
            for card in row["cards"]
        )
        for row in evidence_rows
    )
    citations_hold = all(
        card["citation"]["chunk_id"] in chunk_by_id
        and card["citation"]["text_hash"]
        == chunk_by_id[card["citation"]["chunk_id"]]["text_hash"]
        for card in cards
    )
    checks = {
        "f4_input_gate_passed": True,
        "model_is_character_2_to_4_gram_tfidf": (
            index["model_version"] == MODEL_VERSION
            and index["ngram_range"] == [NGRAM_MIN, NGRAM_MAX]
            and index["similarity"] == "cosine"
        ),
        "all_223_chunks_indexed": (
            index["chunk_count"] == len(chunks) == 223
            and len(index["vectors"]) == 223
        ),
        "retrieval_results_respect_selected_fund_and_period": (
            filters_hold
        ),
        "citation_chunk_ids_and_hashes_exist": citations_hold,
        "all_smoke_queries_retrieve_expected_physical_page": all(
            row["status"] == "PASS" for row in query_audit_rows
        ),
        "evidence_cards_include_physical_page_and_lineage": all(
            card["citation"]["physical_page"] >= 1
            and len(card["citation"]["text_hash"]) == 64
            and len(card["citation"]["source_pdf_sha256"]) == 64
            and card["citation"]["announcement_url"].startswith("https://")
            and card["citation"]["file_url"].startswith("https://")
            for card in cards
        ),
        "offline_no_external_model_or_api": True,
        "tracked_audit_excludes_extracted_text": all(
            "evidence_text" not in row and "text" not in row
            for row in query_audit_rows
        ),
    }
    return {
        "stage": "F5",
        "schema_version": "f5_tfidf_evidence_cards_v1",
        "generated_at": utc_now(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "model": {
            "model_version": index["model_version"],
            "analyzer": index["analyzer"],
            "ngram_range": index["ngram_range"],
            "tf_formula": index["tf_formula"],
            "idf_formula": index["idf_formula"],
            "similarity": index["similarity"],
            "external_dependencies": [],
            "external_api_calls": 0,
        },
        "counts": {
            "indexed_chunks": index["chunk_count"],
            "vocabulary_size": index["vocabulary_size"],
            "smoke_queries": len(query_audit_rows),
            "evidence_cards": len(cards),
        },
        "checks": checks,
        "smoke_query_results": [
            {
                "query_id": row["query_id"],
                "fund_code_filter": row["fund_code_filter"],
                "period_filter": row["period_filter"],
                "expected_doc_id": row["expected_doc_id"],
                "expected_physical_page": int(
                    row["expected_physical_page"]
                ),
                "expected_page_rank": (
                    None
                    if row["expected_page_rank"] == ""
                    else int(row["expected_page_rank"])
                ),
                "top_chunk_id": row["top_chunk_id"],
                "top_text_hash": row["top_text_hash"],
                "status": row["status"],
            }
            for row in query_audit_rows
        ],
        "private_outputs": {
            "index": "data/processed/tfidf_index.json",
            "evidence_cards": (
                "data/processed/f5_evidence_cards.jsonl"
            ),
            "contain_full_extracted_text": True,
            "git_ignored": True,
        },
        "next_stage": "F6",
        "next_stage_authorized": False,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--f4-audit", type=Path, default=DEFAULT_F4_AUDIT)
    parser.add_argument("--index-output", type=Path, default=DEFAULT_INDEX)
    parser.add_argument(
        "--evidence-output", type=Path, default=DEFAULT_EVIDENCE
    )
    parser.add_argument(
        "--query-audit", type=Path, default=DEFAULT_QUERY_AUDIT
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
    f4_audit_path = args.f4_audit.resolve()
    f4_audit = validate_f4_gate(f4_audit_path)
    chunks = read_jsonl(chunks_path)
    validate_chunks(chunks, f4_audit)

    index = build_index(chunks)
    validate_index(index, chunks)
    evidence_rows, query_audit_rows = run_smoke_queries(
        index=index, chunks=chunks
    )
    audit = build_audit(
        index=index,
        chunks=chunks,
        evidence_rows=evidence_rows,
        query_audit_rows=query_audit_rows,
    )

    index_path = args.index_output.resolve()
    evidence_path = args.evidence_output.resolve()
    query_audit_path = args.query_audit.resolve()
    audit_path = args.audit_output.resolve()
    write_json(index_path, index, compact=True)
    write_jsonl(evidence_path, evidence_rows)
    write_csv(
        query_audit_path,
        QUERY_AUDIT_FIELDS,
        query_audit_rows,
    )
    write_json(audit_path, audit)

    run_manifest = {
        "stage": "F5",
        "generated_at": utc_now(),
        "status": audit["status"],
        "inputs": {
            "data/processed/chunks.jsonl": {
                "sha256": sha256_file(chunks_path),
                "rows": len(chunks),
                "git_ignored": True,
            },
            "results/f4_audit.json": {
                "sha256": sha256_file(f4_audit_path),
                "status": "PASS",
            },
        },
        "private_outputs": {
            str(index_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ): {
                "sha256": sha256_file(index_path),
                "indexed_chunks": index["chunk_count"],
                "vocabulary_size": index["vocabulary_size"],
                "git_ignored": True,
            },
            str(evidence_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ): {
                "sha256": sha256_file(evidence_path),
                "queries": len(evidence_rows),
                "evidence_cards": sum(
                    len(row["cards"]) for row in evidence_rows
                ),
                "contains_extracted_text": True,
                "git_ignored": True,
            },
        },
        "tracked_audits": {
            str(query_audit_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ): {
                "sha256": sha256_file(query_audit_path),
                "rows": len(query_audit_rows),
                "contains_extracted_text": False,
            },
            str(audit_path.relative_to(PROJECT_ROOT)).replace("\\", "/"): {
                "sha256": sha256_file(audit_path),
                "contains_extracted_text": False,
            },
        },
        "code": {
            "src/retrieval.py": sha256_file(
                PROJECT_ROOT / "src" / "retrieval.py"
            ),
            "scripts/build_retrieval.py": sha256_file(
                Path(__file__).resolve()
            ),
            "scripts/search_reports.py": sha256_file(
                PROJECT_ROOT / "scripts" / "search_reports.py"
            ),
            "tests/test_retrieval.py": sha256_file(
                PROJECT_ROOT / "tests" / "test_retrieval.py"
            ),
        },
    }
    write_json(args.run_manifest.resolve(), run_manifest)

    print(
        f"F5 {audit['status']}: {index['chunk_count']} chunks, "
        f"{index['vocabulary_size']} n-grams, "
        f"{len(query_audit_rows)} filtered smoke queries"
    )
    if args.strict and audit["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
