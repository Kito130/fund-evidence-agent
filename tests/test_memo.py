from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path

from src.memo import (
    MAX_MEMO_CARDS,
    MEMO_HEADINGS,
    MIN_EVIDENCE_COVERAGE,
    MIN_TOP_SCORE,
    REFUSAL_MESSAGE,
    SYSTEM_NAME,
    assess_evidence,
    build_memo,
    extract_excerpt,
    verify_cards,
)


ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "processed" / "chunks.jsonl"
MEMOS = ROOT / "data" / "processed" / "f6_memos.jsonl"
CASE_AUDIT = ROOT / "results" / "f6_case_audit.csv"
AUDIT = ROOT / "results" / "f6_audit.json"
RUN_MANIFEST = ROOT / "results" / "f6_run_manifest.json"


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


def card(
    *,
    chunk_id: str = "sample",
    text: str = "报告期内重点关注人工智能、半导体和算力产业链。",
    score: float = 0.4,
    fund_code: str = "003567",
    period: str = "2026Q2",
    page: int = 7,
) -> dict:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "rank": 1,
        "score": score,
        "query_hash": "q" * 64,
        "evidence_text": text,
        "citation": {
            "doc_id": f"{fund_code}_{period}",
            "fund_code": fund_code,
            "fund_name": "样例基金",
            "period": period,
            "period_end": "2026-06-30",
            "physical_page": page,
            "chunk_id": chunk_id,
            "text_hash": text_hash,
            "page_text_hash": "p" * 64,
            "source_pdf_sha256": "s" * 64,
            "announcement_url": "https://example.invalid/announcement",
            "file_url": "https://example.invalid/report.pdf",
        },
        "citation_label": (
            f"{fund_code}_{period}｜物理页 {page}｜{chunk_id}"
        ),
    }


class MemoUnitTests(unittest.TestCase):
    def test_required_system_name_and_refusal_are_exact(self):
        self.assertEqual(
            SYSTEM_NAME, "可追溯文档检索与模板化投研 Memo 系统"
        )
        self.assertEqual(
            REFUSAL_MESSAGE, "当前文档不足以回答该问题。"
        )

    def test_evidence_gate_uses_fixed_conservative_thresholds(self):
        self.assertEqual(MIN_TOP_SCORE, 0.05)
        self.assertEqual(MIN_EVIDENCE_COVERAGE, 0.50)
        decision = assess_evidence(
            "人工智能半导体", [card()]
        )
        self.assertTrue(decision["accepted"])

    def test_empty_evidence_is_refused(self):
        decision = assess_evidence("今天天气怎么样", [])
        self.assertFalse(decision["accepted"])
        self.assertIn(
            "no_retrieval_results", decision["reason_codes"]
        )

    def test_low_query_coverage_is_refused_even_with_high_score(self):
        decision = assess_evidence(
            "基金经理的家庭住址是什么",
            [card(score=0.9)],
        )
        self.assertFalse(decision["accepted"])
        self.assertIn(
            "query_coverage_below_threshold",
            decision["reason_codes"],
        )

    def test_excerpt_is_bounded_exact_source_substring(self):
        text = (
            "市场回顾。" + "人工智能产业链保持较高景气度。" * 20
        )
        excerpt = extract_excerpt("人工智能产业链", text)
        self.assertLessEqual(len(excerpt), 180)
        self.assertIn(excerpt, text)

    def test_scope_crossing_card_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_cards(
                [card(fund_code="003834")],
                fund_codes=["003567"],
                periods=["2026Q2"],
            )

    def test_card_text_hash_mismatch_is_rejected(self):
        changed = card()
        changed["citation"]["text_hash"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_cards(
                [changed],
                fund_codes=["003567"],
                periods=["2026Q2"],
            )

    def test_answered_memo_uses_four_sections_in_order(self):
        memo = build_memo(
            "人工智能半导体",
            cards=[card()],
            fund_codes=["003567"],
            periods=["2026Q2"],
        )
        self.assertEqual(memo["status"], "ANSWERED")
        positions = [
            memo["markdown"].index(heading)
            for heading in MEMO_HEADINGS
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(
            all(
                memo["markdown"].count(heading) == 1
                for heading in MEMO_HEADINGS
            )
        )

    def test_answered_fact_excerpt_has_exact_chunk_support(self):
        evidence = card()
        memo = build_memo(
            "人工智能半导体",
            cards=[evidence],
            fund_codes=["003567"],
            periods=["2026Q2"],
        )
        excerpt = memo["fact_excerpts"][0]
        self.assertIn(excerpt["excerpt"], evidence["evidence_text"])
        self.assertEqual(
            excerpt["excerpt_hash"],
            hashlib.sha256(
                excerpt["excerpt"].encode("utf-8")
            ).hexdigest(),
        )
        self.assertEqual(
            excerpt["text_hash"],
            evidence["citation"]["text_hash"],
        )

    def test_refused_memo_is_only_fixed_message_without_citations(self):
        memo = build_memo(
            "今天天气怎么样",
            cards=[],
            fund_codes=["003567"],
            periods=["2026Q2"],
        )
        self.assertEqual(memo["status"], "REFUSED")
        self.assertEqual(memo["markdown"], REFUSAL_MESSAGE)
        self.assertEqual(memo["citations"], [])
        self.assertEqual(memo["fact_excerpts"], [])

    def test_memo_never_uses_more_than_three_cards(self):
        cards = [
            card(chunk_id=f"sample_{index}", page=index)
            for index in range(1, 6)
        ]
        memo = build_memo(
            "人工智能半导体",
            cards=cards,
            fund_codes=["003567"],
            periods=["2026Q2"],
        )
        self.assertEqual(len(memo["citations"]), MAX_MEMO_CARDS)
        self.assertEqual(len(memo["fact_excerpts"]), MAX_MEMO_CARDS)

    def test_memo_does_not_claim_to_be_llm_rag(self):
        memo = build_memo(
            "人工智能半导体",
            cards=[card()],
            fund_codes=["003567"],
            periods=["2026Q2"],
        )
        self.assertNotIn("LLM RAG", memo["markdown"])


@unittest.skipUnless(
    CHUNKS.is_file(),
    "private V1 processed chunks are not distributed in the public repository",
)
class MemoIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = read_jsonl(CHUNKS)
        cls.chunk_by_id = {
            row["chunk_id"]: row for row in cls.chunks
        }
        cls.memos = read_jsonl(MEMOS)
        cls.case_audit = read_csv(CASE_AUDIT)
        cls.audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        cls.run_manifest = json.loads(
            RUN_MANIFEST.read_text(encoding="utf-8")
        )

    def test_f6_audit_and_all_seven_cases_pass(self):
        self.assertEqual(self.audit["stage"], "F6")
        self.assertEqual(self.audit["status"], "PASS")
        self.assertTrue(all(self.audit["checks"].values()))
        self.assertEqual(self.audit["counts"]["smoke_cases"], 7)
        self.assertEqual(self.audit["counts"]["passed_cases"], 7)
        self.assertTrue(
            all(row["status"] == "PASS" for row in self.case_audit)
        )

    def test_private_cases_have_three_answers_and_four_refusals(self):
        statuses = [
            row["memo"]["status"] for row in self.memos
        ]
        self.assertEqual(statuses.count("ANSWERED"), 3)
        self.assertEqual(statuses.count("REFUSED"), 4)
        for row in self.memos:
            memo = row["memo"]
            if memo["status"] == "REFUSED":
                self.assertEqual(memo["markdown"], REFUSAL_MESSAGE)
                self.assertEqual(memo["citations"], [])

    def test_every_answer_excerpt_is_supported_by_its_chunk(self):
        for row in self.memos:
            memo = row["memo"]
            for excerpt in memo["fact_excerpts"]:
                chunk = self.chunk_by_id[excerpt["chunk_id"]]
                self.assertIn(excerpt["excerpt"], chunk["text"])
                self.assertEqual(excerpt["text_hash"], chunk["text_hash"])

    def test_tracked_f6_audits_exclude_queries_and_excerpts(self):
        self.assertLess(AUDIT.stat().st_size, 100_000)
        serialized = json.dumps(self.audit, ensure_ascii=False)
        self.assertNotIn('"query":', serialized)
        self.assertNotIn('"excerpt"', serialized)
        self.assertNotIn("人工智能产业链", serialized)
        csv_text = CASE_AUDIT.read_text(encoding="utf-8")
        self.assertNotIn("家庭住址", csv_text)
        self.assertNotIn("天气怎么样", csv_text)

    def test_f6_run_manifest_hashes_match_outputs_and_code(self):
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

    def test_private_memo_outputs_are_git_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/processed/", ignored)


if __name__ == "__main__":
    unittest.main()
