"""Rule-based, citation-constrained Markdown Memo generation for F6."""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from src.retrieval import character_ngrams, retrieve, sha256_text


SYSTEM_NAME = "可追溯文档检索与模板化投研 Memo 系统"
REFUSAL_MESSAGE = "当前文档不足以回答该问题。"
MIN_TOP_SCORE = 0.05
MIN_EVIDENCE_COVERAGE = 0.50
MAX_EXCERPT_CHARS = 180
MAX_MEMO_CARDS = 3
MEMO_HEADINGS = (
    "## 已确认事实",
    "## 原文证据",
    "## 研究含义",
    "## 当前无法确认的内容",
)


def _selected(values: Iterable[str], *, field: str) -> set[str]:
    selected = {str(value) for value in values if str(value)}
    if not selected:
        raise ValueError(f"{field} selection cannot be empty")
    return selected


def verify_cards(
    cards: Sequence[dict],
    *,
    fund_codes: Iterable[str],
    periods: Iterable[str],
) -> None:
    selected_funds = _selected(fund_codes, field="fund_code")
    selected_periods = _selected(periods, field="period")
    for card in cards:
        citation = card.get("citation", {})
        if (
            citation.get("fund_code") not in selected_funds
            or citation.get("period") not in selected_periods
        ):
            raise ValueError("evidence card crosses the selected scope")
        if not citation.get("chunk_id"):
            raise ValueError("evidence card has no chunk_id")
        evidence_text = str(card.get("evidence_text", ""))
        if (
            not evidence_text
            or sha256_text(evidence_text) != citation.get("text_hash")
        ):
            raise ValueError("evidence card text hash mismatch")


def assess_evidence(
    query: str,
    cards: Sequence[dict],
    *,
    minimum_top_score: float = MIN_TOP_SCORE,
    minimum_evidence_coverage: float = MIN_EVIDENCE_COVERAGE,
) -> dict:
    query_grams = set(character_ngrams(query))
    evidence_grams = {
        gram
        for card in cards
        for gram in character_ngrams(str(card.get("evidence_text", "")))
    }
    coverage = (
        len(query_grams & evidence_grams) / len(query_grams)
        if query_grams
        else 0.0
    )
    top_score = max(
        (float(card.get("score", 0.0)) for card in cards),
        default=0.0,
    )
    reasons = []
    if not cards:
        reasons.append("no_retrieval_results")
    if top_score < minimum_top_score:
        reasons.append("top_score_below_threshold")
    if coverage < minimum_evidence_coverage:
        reasons.append("query_coverage_below_threshold")
    return {
        "accepted": not reasons,
        "reason_codes": reasons or ["accepted"],
        "top_score": top_score,
        "query_ngram_count": len(query_grams),
        "matched_query_ngram_count": len(query_grams & evidence_grams),
        "evidence_coverage": coverage,
        "minimum_top_score": minimum_top_score,
        "minimum_evidence_coverage": minimum_evidence_coverage,
    }


def _candidate_windows(text: str, max_chars: int) -> list[str]:
    segments = [
        segment.strip()
        for segment in re.split(
            r"(?<=[。！？；])|\n|\s+\|\s+",
            text,
        )
        if segment.strip()
    ]
    candidates = []
    step = max(1, max_chars - 40)
    for segment in segments:
        if len(segment) <= max_chars:
            candidates.append(segment)
            continue
        for start in range(0, len(segment), step):
            window = segment[start : start + max_chars]
            if window:
                candidates.append(window)
            if start + max_chars >= len(segment):
                break
    if not candidates and text:
        candidates.append(text[:max_chars])
    return candidates


def extract_excerpt(
    query: str,
    evidence_text: str,
    *,
    max_chars: int = MAX_EXCERPT_CHARS,
) -> str:
    if max_chars <= 0:
        raise ValueError("max excerpt length must be positive")
    if not evidence_text:
        raise ValueError("cannot extract from empty evidence")
    query_grams = set(character_ngrams(query))
    candidates = _candidate_windows(evidence_text, max_chars)

    def score(item: tuple[int, str]) -> tuple[float, float, int]:
        index, candidate = item
        candidate_grams = set(character_ngrams(candidate))
        overlap = len(query_grams & candidate_grams)
        density = (
            overlap / len(candidate_grams) if candidate_grams else 0.0
        )
        return float(overlap), density, -index

    _, excerpt = max(enumerate(candidates), key=score)
    if excerpt not in evidence_text:
        raise ValueError("excerpt is not an exact evidence substring")
    return excerpt


def _memo_markdown(query: str, cards: Sequence[dict]) -> tuple[str, list]:
    facts = []
    evidence = []
    excerpts = []
    for index, card in enumerate(cards[:MAX_MEMO_CARDS], start=1):
        citation = card["citation"]
        excerpt = extract_excerpt(query, card["evidence_text"])
        label = card["citation_label"]
        facts.append(f"- {excerpt}（引用：{label}）")
        evidence.append(
            "\n".join(
                (
                    f"- 证据 {index}：{label}",
                    f"  - 余弦相似度：{float(card['score']):.6f}",
                    f"  - 文本 SHA-256：{citation['text_hash']}",
                    f"  > {excerpt}",
                )
            )
        )
        excerpts.append(
            {
                "rank": index,
                "excerpt": excerpt,
                "excerpt_hash": sha256_text(excerpt),
                "chunk_id": citation["chunk_id"],
                "text_hash": citation["text_hash"],
                "physical_page": citation["physical_page"],
            }
        )

    selected_funds = sorted(
        {card["citation"]["fund_code"] for card in cards}
    )
    selected_periods = sorted(
        {card["citation"]["period"] for card in cards}
    )
    implications = [
        (
            "- 以上证据只支持对所选基金 "
            f"{'、'.join(selected_funds)} 在报告期 "
            f"{'、'.join(selected_periods)} 内披露内容的归纳。"
        ),
        (
            "- 检索分数只表示文本相关性，不代表事实重要性、"
            "完整持仓判断、收益预测或投资建议。"
        ),
    ]
    limitations = [
        (
            "- 当前证据不能确认报告未披露的完整持仓、所选报告期以外的变化、"
            "未来收益或管理人的未公开意图。"
        ),
        (
            "- 若需要更强结论，应补充对应期间的官方披露并重新检索，"
            "不能用相似文本代替证据。"
        ),
    ]
    markdown = "\n\n".join(
        (
            MEMO_HEADINGS[0] + "\n\n" + "\n".join(facts),
            MEMO_HEADINGS[1] + "\n\n" + "\n\n".join(evidence),
            MEMO_HEADINGS[2] + "\n\n" + "\n".join(implications),
            MEMO_HEADINGS[3] + "\n\n" + "\n".join(limitations),
        )
    )
    return markdown + "\n", excerpts


def build_memo(
    query: str,
    *,
    cards: Sequence[dict],
    fund_codes: Iterable[str],
    periods: Iterable[str],
) -> dict:
    selected_funds = sorted(_selected(fund_codes, field="fund_code"))
    selected_periods = sorted(_selected(periods, field="period"))
    effective_cards = list(cards[:MAX_MEMO_CARDS])
    verify_cards(
        effective_cards,
        fund_codes=selected_funds,
        periods=selected_periods,
    )
    decision = assess_evidence(query, effective_cards)
    base = {
        "system_name": SYSTEM_NAME,
        "query": query,
        "query_hash": sha256_text(query),
        "fund_code_filter": selected_funds,
        "period_filter": selected_periods,
        "decision": decision,
    }
    if not decision["accepted"]:
        return {
            **base,
            "status": "REFUSED",
            "markdown": REFUSAL_MESSAGE,
            "citations": [],
            "fact_excerpts": [],
        }

    markdown, excerpts = _memo_markdown(query, effective_cards)
    return {
        **base,
        "status": "ANSWERED",
        "markdown": markdown,
        "citations": [card["citation"] for card in effective_cards],
        "fact_excerpts": excerpts,
    }


def retrieve_and_build_memo(
    query: str,
    *,
    index: dict,
    chunks: Sequence[dict],
    fund_codes: Iterable[str],
    periods: Iterable[str],
    top_k: int = MAX_MEMO_CARDS,
) -> dict:
    selected_funds = list(fund_codes)
    selected_periods = list(periods)
    cards = retrieve(
        query,
        index=index,
        chunks=chunks,
        fund_codes=selected_funds,
        periods=selected_periods,
        top_k=top_k,
    )
    return build_memo(
        query,
        cards=cards,
        fund_codes=selected_funds,
        periods=selected_periods,
    )
