"""Offline Chinese character n-gram TF-IDF retrieval for F5."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Iterable, Sequence


MODEL_VERSION = "f5_char_ngram_tfidf_v1"
NGRAM_MIN = 2
NGRAM_MAX = 4
DEFAULT_TOP_K = 3
MAX_TOP_K = 10

SEARCHABLE_CHARACTER = re.compile(r"[0-9a-z\u4e00-\u9fff]")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_for_search(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(SEARCHABLE_CHARACTER.findall(normalized))


def character_ngrams(
    text: str,
    *,
    ngram_min: int = NGRAM_MIN,
    ngram_max: int = NGRAM_MAX,
) -> list[str]:
    if ngram_min <= 0 or ngram_max < ngram_min:
        raise ValueError("invalid character n-gram range")
    normalized = normalize_for_search(text)
    return [
        normalized[start : start + width]
        for width in range(ngram_min, ngram_max + 1)
        for start in range(0, len(normalized) - width + 1)
    ]


def _sublinear_tf(count: int) -> float:
    if count <= 0:
        raise ValueError("term frequency must be positive")
    return 1.0 + math.log(count)


def _unit_normalize(weights: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(value * value for value in weights.values()))
    if norm == 0:
        return {}
    return {
        term: value / norm
        for term, value in sorted(weights.items())
    }


def build_index(chunks: Sequence[dict]) -> dict:
    if not chunks:
        raise ValueError("cannot build a retrieval index without chunks")
    chunk_ids = [str(chunk["chunk_id"]) for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("chunk_id values must be unique")

    counts_by_chunk: list[Counter[str]] = []
    document_frequency: Counter[str] = Counter()
    for chunk in chunks:
        counts = Counter(character_ngrams(str(chunk["text"])))
        if not counts:
            raise ValueError(f"{chunk['chunk_id']}: no searchable text")
        counts_by_chunk.append(counts)
        document_frequency.update(counts.keys())

    chunk_count = len(chunks)
    idf = {
        term: math.log(
            (1.0 + chunk_count) / (1.0 + frequency)
        )
        + 1.0
        for term, frequency in sorted(document_frequency.items())
    }

    vectors = []
    for chunk, counts in zip(chunks, counts_by_chunk):
        weights = _unit_normalize(
            {
                term: _sublinear_tf(count) * idf[term]
                for term, count in counts.items()
            }
        )
        vectors.append(
            {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "fund_code": chunk["fund_code"],
                "period": chunk["period"],
                "page_number": int(chunk["page_number"]),
                "text_hash": chunk["text_hash"],
                "weights": weights,
            }
        )

    return {
        "model_version": MODEL_VERSION,
        "analyzer": "normalized Chinese/alphanumeric character n-gram",
        "ngram_range": [NGRAM_MIN, NGRAM_MAX],
        "tf_formula": "1 + ln(count)",
        "idf_formula": "ln((1 + N) / (1 + df)) + 1",
        "similarity": "cosine",
        "chunk_count": chunk_count,
        "vocabulary_size": len(idf),
        "idf_values": idf,
        "vectors": vectors,
    }


def validate_index(index: dict, chunks: Sequence[dict]) -> None:
    if index.get("model_version") != MODEL_VERSION:
        raise ValueError("unexpected retrieval model version")
    if index.get("ngram_range") != [NGRAM_MIN, NGRAM_MAX]:
        raise ValueError("retrieval index does not use 2-4 grams")
    if int(index.get("chunk_count", -1)) != len(chunks):
        raise ValueError("retrieval index chunk count mismatch")
    chunk_by_id = {
        str(chunk["chunk_id"]): chunk for chunk in chunks
    }
    vectors = index.get("vectors", [])
    if len(vectors) != len(chunks):
        raise ValueError("retrieval vector count mismatch")
    if {item["chunk_id"] for item in vectors} != set(chunk_by_id):
        raise ValueError("retrieval index chunk inventory mismatch")
    for vector in vectors:
        chunk = chunk_by_id[vector["chunk_id"]]
        if (
            vector["doc_id"] != chunk["doc_id"]
            or vector["fund_code"] != chunk["fund_code"]
            or vector["period"] != chunk["period"]
            or int(vector["page_number"]) != int(chunk["page_number"])
            or vector["text_hash"] != chunk["text_hash"]
        ):
            raise ValueError(
                f"{vector['chunk_id']}: retrieval metadata drift"
            )
        norm = math.sqrt(
            sum(
                float(value) * float(value)
                for value in vector["weights"].values()
            )
        )
        if not math.isclose(norm, 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError(
                f"{vector['chunk_id']}: TF-IDF vector is not unit length"
            )


def query_vector(query: str, idf: dict[str, float]) -> dict[str, float]:
    if not normalize_for_search(query):
        raise ValueError("query has no searchable characters")
    counts = Counter(character_ngrams(query))
    weights = {
        term: _sublinear_tf(count) * float(idf[term])
        for term, count in counts.items()
        if term in idf
    }
    return _unit_normalize(weights)


def _validated_filter(
    values: Iterable[str] | None, *, field: str
) -> set[str]:
    if values is None:
        raise ValueError(f"{field} filter is required")
    selected = {str(value) for value in values if str(value)}
    if not selected:
        raise ValueError(f"{field} filter cannot be empty")
    return selected


def retrieve(
    query: str,
    *,
    index: dict,
    chunks: Sequence[dict],
    fund_codes: Iterable[str] | None,
    periods: Iterable[str] | None,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict]:
    if not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")
    selected_funds = _validated_filter(
        fund_codes, field="fund_code"
    )
    selected_periods = _validated_filter(periods, field="period")
    chunk_by_id = {
        str(chunk["chunk_id"]): chunk for chunk in chunks
    }
    q_vector = query_vector(query, index["idf_values"])
    if not q_vector:
        return []

    scored = []
    for vector in index["vectors"]:
        if (
            vector["fund_code"] not in selected_funds
            or vector["period"] not in selected_periods
        ):
            continue
        score = sum(
            q_weight * float(vector["weights"].get(term, 0.0))
            for term, q_weight in q_vector.items()
        )
        if score <= 0:
            continue
        chunk = chunk_by_id[vector["chunk_id"]]
        scored.append(
            {
                "score": score,
                "chunk": chunk,
            }
        )
    scored.sort(
        key=lambda item: (
            -item["score"],
            item["chunk"]["doc_id"],
            int(item["chunk"]["page_number"]),
            item["chunk"]["chunk_id"],
        )
    )

    results = []
    query_hash = sha256_text(query)
    for rank, item in enumerate(scored[:top_k], start=1):
        chunk = item["chunk"]
        physical_page = int(chunk["page_number"])
        results.append(
            {
                "rank": rank,
                "score": item["score"],
                "query_hash": query_hash,
                "evidence_text": chunk["text"],
                "citation": {
                    "doc_id": chunk["doc_id"],
                    "fund_code": chunk["fund_code"],
                    "fund_name": chunk["fund_name"],
                    "period": chunk["period"],
                    "period_end": chunk["period_end"],
                    "physical_page": physical_page,
                    "chunk_id": chunk["chunk_id"],
                    "text_hash": chunk["text_hash"],
                    "page_text_hash": chunk["page_text_hash"],
                    "source_pdf_sha256": chunk[
                        "source_pdf_sha256"
                    ],
                    "announcement_url": chunk["announcement_url"],
                    "file_url": chunk["file_url"],
                },
                "citation_label": (
                    f"{chunk['doc_id']}｜物理页 {physical_page}｜"
                    f"{chunk['chunk_id']}"
                ),
            }
        )
    return results
