from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Any, Final

from .errors import ToolError, ToolErrorCode

MODEL_VERSION: Final = "f5_char_ngram_tfidf_v1"
SEARCHABLE_CHARACTER = re.compile(r"[0-9a-z\u4e00-\u9fff]")
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            r"ignore\s+(all\s+)?(previous|system)|忽略.{0,8}(指令|规则)",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_exfiltration",
        re.compile(r"api[ _-]?key|secret|token|密钥|凭证", re.IGNORECASE),
    ),
    (
        "tool_escalation",
        re.compile(
            r"shell|subprocess|execute command|执行.{0,6}(命令|脚本)",
            re.IGNORECASE,
        ),
    ),
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_for_search(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(SEARCHABLE_CHARACTER.findall(normalized))


def character_ngrams(text: str, *, minimum: int = 2, maximum: int = 4) -> list[str]:
    normalized = normalize_for_search(text)
    return [
        normalized[start : start + width]
        for width in range(minimum, maximum + 1)
        for start in range(len(normalized) - width + 1)
    ]


def _unit_normalize(weights: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(value * value for value in weights.values()))
    if norm == 0:
        return {}
    return {term: value / norm for term, value in sorted(weights.items())}


def query_vector(query: str, idf: dict[str, Any]) -> dict[str, float]:
    if not normalize_for_search(query):
        raise ToolError(
            ToolErrorCode.INVALID_INPUT, "query has no searchable characters"
        )
    counts = Counter(character_ngrams(query))
    return _unit_normalize(
        {
            term: (1.0 + math.log(count)) * float(idf[term])
            for term, count in counts.items()
            if term in idf
        }
    )


def validate_index(index: dict[str, Any], chunks: list[dict[str, Any]]) -> None:
    if index.get("model_version") != MODEL_VERSION:
        raise ToolError(
            ToolErrorCode.DATA_INTEGRITY, "retrieval model version mismatch"
        )
    if int(index.get("chunk_count", -1)) != len(chunks):
        raise ToolError(ToolErrorCode.DATA_INTEGRITY, "retrieval chunk count mismatch")
    chunk_by_id = {str(chunk["chunk_id"]): chunk for chunk in chunks}
    vectors = index.get("vectors")
    if not isinstance(vectors, list) or len(vectors) != len(chunks):
        raise ToolError(
            ToolErrorCode.DATA_INTEGRITY, "retrieval vector inventory mismatch"
        )
    for vector in vectors:
        if not isinstance(vector, dict):
            raise ToolError(ToolErrorCode.DATA_INTEGRITY, "retrieval vector is invalid")
        chunk = chunk_by_id.get(str(vector.get("chunk_id")))
        if chunk is None:
            raise ToolError(ToolErrorCode.DATA_INTEGRITY, "retrieval chunk ID mismatch")
        fields = ("doc_id", "fund_code", "period", "text_hash")
        if any(str(vector.get(field)) != str(chunk.get(field)) for field in fields):
            raise ToolError(ToolErrorCode.DATA_INTEGRITY, "retrieval metadata drift")


def retrieve(
    query: str,
    *,
    index: dict[str, Any],
    chunks: list[dict[str, Any]],
    fund_codes: set[str],
    periods: set[str],
    top_k: int,
) -> list[tuple[float, dict[str, Any]]]:
    validate_index(index, chunks)
    idf = index.get("idf_values")
    vectors = index.get("vectors")
    if not isinstance(idf, dict) or not isinstance(vectors, list):
        raise ToolError(ToolErrorCode.DATA_INTEGRITY, "retrieval index fields missing")
    q_vector = query_vector(query, idf)
    if not q_vector:
        return []
    chunk_by_id = {str(chunk["chunk_id"]): chunk for chunk in chunks}
    scored: list[tuple[float, dict[str, Any]]] = []
    for vector in vectors:
        if not isinstance(vector, dict):
            continue
        if str(vector.get("fund_code")) not in fund_codes:
            continue
        if str(vector.get("period")) not in periods:
            continue
        weights = vector.get("weights")
        if not isinstance(weights, dict):
            raise ToolError(ToolErrorCode.DATA_INTEGRITY, "vector weights missing")
        score = sum(
            q_weight * float(weights.get(term, 0.0))
            for term, q_weight in q_vector.items()
        )
        if score > 0:
            scored.append((score, chunk_by_id[str(vector["chunk_id"])]))
    scored.sort(
        key=lambda item: (
            -item[0],
            str(item[1]["doc_id"]),
            int(item[1]["page_number"]),
            str(item[1]["chunk_id"]),
        )
    )
    return scored[:top_k]


def detect_injection_signals(text: str) -> list[str]:
    return [name for name, pattern in INJECTION_PATTERNS if pattern.search(text)]
