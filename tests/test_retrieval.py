from __future__ import annotations

import copy
import csv
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

from src.retrieval import (
    MODEL_VERSION,
    build_index,
    character_ngrams,
    normalize_for_search,
    retrieve,
    validate_index,
)


ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "processed" / "chunks.jsonl"
INDEX = ROOT / "data" / "processed" / "tfidf_index.json"
EVIDENCE = (
    ROOT / "data" / "processed" / "f5_evidence_cards.jsonl"
)
QUERY_AUDIT = ROOT / "results" / "f5_query_audit.csv"
AUDIT = ROOT / "results" / "f5_audit.json"
RUN_MANIFEST = ROOT / "results" / "f5_run_manifest.json"
SEARCH_SCRIPT = ROOT / "scripts" / "search_reports.py"


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def synthetic_chunk(
    *,
    chunk_id: str,
    fund_code: str,
    period: str,
    text: str,
    page: int = 1,
) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": f"{fund_code}_{period}",
        "fund_code": fund_code,
        "fund_name": f"基金{fund_code}",
        "period": period,
        "period_end": "2026-06-30",
        "page_number": page,
        "text": text,
        "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "page_text_hash": "a" * 64,
        "source_pdf_sha256": "b" * 64,
        "announcement_url": "https://example.invalid/announcement",
        "file_url": "https://example.invalid/report.pdf",
    }


class RetrievalUnitTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [
            synthetic_chunk(
                chunk_id="ai",
                fund_code="001",
                period="2026Q2",
                text="人工智能产业链、半导体和算力投资分析",
            ),
            synthetic_chunk(
                chunk_id="energy",
                fund_code="002",
                period="2026Q2",
                text="新能源电池、电力设备和储能投资分析",
            ),
            synthetic_chunk(
                chunk_id="old_ai",
                fund_code="001",
                period="2025Q4",
                text="人工智能软件服务投资分析",
            ),
        ]
        self.index = build_index(self.chunks)

    def test_normalization_removes_spacing_and_punctuation(self):
        self.assertEqual(
            normalize_for_search("ＡI 基金，报告！"), "ai基金报告"
        )

    def test_character_ngrams_use_exact_two_to_four_range(self):
        grams = character_ngrams("基金报告")
        self.assertEqual(
            grams,
            [
                "基金",
                "金报",
                "报告",
                "基金报",
                "金报告",
                "基金报告",
            ],
        )

    def test_invalid_ngram_range_is_rejected(self):
        with self.assertRaises(ValueError):
            character_ngrams("基金", ngram_min=4, ngram_max=2)

    def test_index_uses_unit_length_vectors(self):
        validate_index(self.index, self.chunks)
        self.assertEqual(self.index["model_version"], MODEL_VERSION)
        self.assertEqual(self.index["ngram_range"], [2, 4])
        self.assertEqual(self.index["similarity"], "cosine")

    def test_retrieval_ranks_relevant_filtered_chunk_first(self):
        results = retrieve(
            "人工智能半导体",
            index=self.index,
            chunks=self.chunks,
            fund_codes=["001"],
            periods=["2026Q2"],
            top_k=3,
        )
        self.assertEqual(results[0]["citation"]["chunk_id"], "ai")

    def test_retrieval_never_crosses_selected_fund_or_period(self):
        results = retrieve(
            "投资分析",
            index=self.index,
            chunks=self.chunks,
            fund_codes=["001"],
            periods=["2026Q2"],
            top_k=3,
        )
        self.assertTrue(results)
        self.assertTrue(
            all(
                item["citation"]["fund_code"] == "001"
                and item["citation"]["period"] == "2026Q2"
                for item in results
            )
        )

    def test_filters_and_top_k_are_mandatory_and_bounded(self):
        with self.assertRaises(ValueError):
            retrieve(
                "投资",
                index=self.index,
                chunks=self.chunks,
                fund_codes=None,
                periods=["2026Q2"],
            )
        with self.assertRaises(ValueError):
            retrieve(
                "投资",
                index=self.index,
                chunks=self.chunks,
                fund_codes=["001"],
                periods=["2026Q2"],
                top_k=11,
            )

    def test_unknown_query_terms_return_no_evidence(self):
        results = retrieve(
            "zzzzzzzz",
            index=self.index,
            chunks=self.chunks,
            fund_codes=["001"],
            periods=["2026Q2"],
        )
        self.assertEqual(results, [])

    def test_index_validation_detects_metadata_drift(self):
        changed = copy.deepcopy(self.index)
        changed["vectors"][0]["period"] = "2099Q4"
        with self.assertRaises(ValueError):
            validate_index(changed, self.chunks)


@unittest.skipUnless(
    CHUNKS.is_file(),
    "private V1 processed retrieval artifacts are not distributed in the public repository",
)
class RetrievalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = read_jsonl(CHUNKS)
        cls.chunk_by_id = {
            row["chunk_id"]: row for row in cls.chunks
        }
        cls.index = json.loads(INDEX.read_text(encoding="utf-8"))
        cls.evidence = read_jsonl(EVIDENCE)
        cls.query_audit = read_csv(QUERY_AUDIT)
        cls.audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        cls.run_manifest = json.loads(
            RUN_MANIFEST.read_text(encoding="utf-8")
        )

    def test_full_index_matches_frozen_f4_chunks(self):
        validate_index(self.index, self.chunks)
        self.assertEqual(len(self.chunks), 223)
        self.assertEqual(self.index["chunk_count"], 223)
        self.assertGreater(self.index["vocabulary_size"], 10000)

    def test_index_metadata_keeps_citation_identity(self):
        for vector in self.index["vectors"]:
            chunk = self.chunk_by_id[vector["chunk_id"]]
            self.assertEqual(vector["doc_id"], chunk["doc_id"])
            self.assertEqual(
                vector["page_number"], chunk["page_number"]
            )
            self.assertEqual(vector["text_hash"], chunk["text_hash"])

    def test_six_smoke_queries_pass(self):
        self.assertEqual(len(self.query_audit), 6)
        self.assertTrue(
            all(row["status"] == "PASS" for row in self.query_audit)
        )
        self.assertTrue(
            all(row["expected_page_rank"] == "1" for row in self.query_audit)
        )

    def test_saved_evidence_cards_respect_every_filter(self):
        self.assertEqual(len(self.evidence), 6)
        for row in self.evidence:
            self.assertEqual(len(row["cards"]), 3)
            for card in row["cards"]:
                citation = card["citation"]
                self.assertIn(
                    citation["fund_code"], row["fund_code_filter"]
                )
                self.assertIn(
                    citation["period"], row["period_filter"]
                )
                self.assertIn(
                    citation["chunk_id"], self.chunk_by_id
                )
                self.assertEqual(
                    citation["text_hash"],
                    self.chunk_by_id[citation["chunk_id"]]["text_hash"],
                )

    def test_f5_stage_audit_passes_without_source_text(self):
        self.assertEqual(self.audit["stage"], "F5")
        self.assertEqual(self.audit["status"], "PASS")
        self.assertTrue(all(self.audit["checks"].values()))
        self.assertLess(AUDIT.stat().st_size, 100_000)
        self.assertNotIn("idf_values", self.audit["model"])
        self.assertNotIn("vectors", self.audit["model"])
        serialized = json.dumps(self.audit, ensure_ascii=False)
        self.assertNotIn('"evidence_text"', serialized)
        self.assertNotIn('"text":', serialized)
        self.assertNotIn("人工智能产业链", serialized)

    def test_search_cli_rejects_unknown_selected_values(self):
        spec = importlib.util.spec_from_file_location(
            "search_reports", SEARCH_SCRIPT
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with self.assertRaises(ValueError):
            module.validate_selected_values(
                chunks=self.chunks,
                fund_codes=["999999"],
                periods=["2026Q2"],
            )
        with self.assertRaises(ValueError):
            module.validate_selected_values(
                chunks=self.chunks,
                fund_codes=["003567"],
                periods=["2099Q4"],
            )

    def test_f5_run_manifest_hashes_match_outputs_and_code(self):
        for section in ("private_outputs", "tracked_audits", "code"):
            for relative_path, metadata in self.run_manifest[
                section
            ].items():
                expected = (
                    metadata
                    if isinstance(metadata, str)
                    else metadata["sha256"]
                )
                self.assertEqual(
                    sha256_file(ROOT / relative_path), expected
                )

    def test_private_retrieval_outputs_are_git_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/processed/", ignored)


if __name__ == "__main__":
    unittest.main()
