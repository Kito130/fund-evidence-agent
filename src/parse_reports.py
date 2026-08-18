"""PyMuPDF page cleaning and page-bounded chunking for F4."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from typing import Iterable

try:
    import fitz
except ImportError:  # pragma: no cover - exercised by CLI dependency guard
    fitz = None


MIN_CHUNK_CHARS = 400
MAX_CHUNK_CHARS = 800
CHUNK_OVERLAP_CHARS = 60
MAX_ALLOWED_OVERLAP = 80
MARGIN_RATIO = 0.12
PARSER_VERSION = "f4_pymupdf_v1"

HEADING_PATTERN = re.compile(
    r"^(?:"
    r"§\s*\d+"
    r"|\d+(?:\.\d+){0,4}\s+"
    r"|[一二三四五六七八九十]+、"
    r"|附录(?:一|二|三|四|\d+)?"
    r")"
)
SENTENCE_END_PATTERN = re.compile(r"[。！？；：]$")
PAGE_NUMBER_PATTERN = re.compile(
    r"^(?:第\s*)?\d+(?:\s*页)?(?:\s*/\s*\d+)?$"
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_spacing(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text).strip()
    text = re.sub(r"\s+([，。！？；：、）】》％%])", r"\1", text)
    text = re.sub(r"([（【《])\s+", r"\1", text)
    text = re.sub(
        r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text
    )
    text = re.sub(
        r"(?<=[0-9A-Za-z])\s+(?=[\u4e00-\u9fff])", "", text
    )
    text = re.sub(
        r"(?<=[\u4e00-\u9fff])\s+(?=[0-9A-Za-z])", "", text
    )
    return text


def canonical_margin_line(text: str) -> str:
    return re.sub(r"\s+", "", normalize_spacing(text))


def is_heading(text: str) -> bool:
    return bool(HEADING_PATTERN.match(text))


def _raw_text_blocks(page) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for raw in page.get_text("blocks", sort=True):
        if int(raw[6]) != 0:
            continue
        lines = [
            normalize_spacing(line)
            for line in raw[4].splitlines()
            if normalize_spacing(line)
        ]
        if not lines:
            continue
        blocks.append(
            {
                "y0": float(raw[1]),
                "y1": float(raw[3]),
                "lines": lines,
            }
        )
    return blocks


def detect_repeated_margin_lines(document) -> set[str]:
    pages_by_line: dict[str, set[int]] = defaultdict(set)
    for page_index, page in enumerate(document):
        height = float(page.rect.height)
        for block in _raw_text_blocks(page):
            in_margin = (
                float(block["y1"]) <= height * MARGIN_RATIO
                or float(block["y0"]) >= height * (1 - MARGIN_RATIO)
            )
            if not in_margin:
                continue
            for line in block["lines"]:
                canonical = canonical_margin_line(str(line))
                if len(canonical) >= 6:
                    pages_by_line[canonical].add(page_index)
    threshold = max(3, math.ceil(len(document) * 0.5))
    return {
        line
        for line, page_indexes in pages_by_line.items()
        if len(page_indexes) >= threshold
    }


def _looks_like_table_block(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    short_ratio = sum(len(line) <= 24 for line in lines) / len(lines)
    numeric_ratio = sum(
        bool(re.search(r"\d|[-—]", line)) for line in lines
    ) / len(lines)
    return short_ratio >= 0.6 and numeric_ratio >= 0.25


def _join_narrative_lines(lines: Iterable[str]) -> str:
    output = ""
    for line in lines:
        if not output:
            output = line
            continue
        spacer = (
            " "
            if output[-1:].isascii()
            and output[-1:].isalnum()
            and line[:1].isascii()
            and line[:1].isalnum()
            else ""
        )
        output += spacer + line
    return normalize_spacing(output)


def clean_page(document, page_index: int, repeated_lines: set[str]) -> dict:
    page = document[page_index]
    height = float(page.rect.height)
    cleaned_blocks: list[tuple[str, bool]] = []
    removed_margin_lines: list[str] = []

    for block in _raw_text_blocks(page):
        block_lines: list[str] = []
        for line in block["lines"]:
            canonical = canonical_margin_line(str(line))
            in_margin = (
                float(block["y1"]) <= height * MARGIN_RATIO
                or float(block["y0"]) >= height * (1 - MARGIN_RATIO)
            )
            is_page_number = (
                float(block["y0"]) >= height * (1 - MARGIN_RATIO)
                and PAGE_NUMBER_PATTERN.fullmatch(canonical) is not None
            )
            if in_margin and (
                canonical in repeated_lines or is_page_number
            ):
                removed_margin_lines.append(str(line))
                continue
            block_lines.append(str(line))
        if not block_lines:
            continue
        table_like = _looks_like_table_block(block_lines)
        if table_like:
            text = " | ".join(block_lines)
        else:
            text = _join_narrative_lines(block_lines)
        if text:
            cleaned_blocks.append((text, table_like))

    paragraphs: list[str] = []
    narrative_buffer = ""
    for text, table_like in cleaned_blocks:
        if table_like or is_heading(text):
            if narrative_buffer:
                paragraphs.append(narrative_buffer)
                narrative_buffer = ""
            paragraphs.append(text)
            continue
        if narrative_buffer:
            spacer = (
                " "
                if narrative_buffer[-1:].isascii()
                and narrative_buffer[-1:].isalnum()
                and text[:1].isascii()
                and text[:1].isalnum()
                else ""
            )
            narrative_buffer += spacer + text
        else:
            narrative_buffer = text
        if SENTENCE_END_PATTERN.search(narrative_buffer):
            paragraphs.append(narrative_buffer)
            narrative_buffer = ""
    if narrative_buffer:
        paragraphs.append(narrative_buffer)

    clean_text = "\n".join(
        normalize_spacing(paragraph)
        for paragraph in paragraphs
        if normalize_spacing(paragraph)
    )
    return {
        "page_number": page_index + 1,
        "clean_text": clean_text,
        "text_hash": sha256_text(clean_text),
        "char_count": len(clean_text),
        "non_whitespace_char_count": len(
            re.sub(r"\s+", "", clean_text)
        ),
        "removed_margin_line_count": len(removed_margin_lines),
        "removed_margin_lines": removed_margin_lines,
    }


def _boundary_before(
    text: str, start: int, lower: int, upper: int
) -> int:
    candidates = []
    for marker in ("\n", "。", "！", "？", "；"):
        position = text.rfind(marker, lower, upper)
        if position >= lower:
            candidates.append(position + 1)
    return max(candidates) if candidates else upper


def split_page_text(
    text: str,
    *,
    min_chars: int = MIN_CHUNK_CHARS,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> list[dict[str, object]]:
    if max_chars <= 0 or min_chars <= 0:
        raise ValueError("chunk sizes must be positive")
    if min_chars > max_chars:
        raise ValueError("minimum chunk size exceeds maximum")
    if not 0 <= overlap_chars <= MAX_ALLOWED_OVERLAP:
        raise ValueError("chunk overlap is outside the allowed range")
    if not text:
        return []
    if len(text) <= max_chars:
        return [
            {
                "text_start": 0,
                "text_end": len(text),
                "leading_overlap_chars": 0,
                "text": text,
            }
        ]

    chunks: list[dict[str, object]] = []
    start = 0
    previous_end = 0
    while start < len(text):
        remaining = len(text) - start
        if remaining <= max_chars:
            end = len(text)
        else:
            upper = min(len(text), start + max_chars)
            lower = min(upper, start + min_chars)
            end = _boundary_before(text, start, lower, upper)

            final_length = len(text) - (end - overlap_chars)
            if final_length < min_chars:
                latest_end = len(text) + overlap_chars - min_chars
                if latest_end >= start + min_chars:
                    end = _boundary_before(
                        text,
                        start,
                        start + min_chars,
                        min(upper, latest_end),
                    )
        if end <= start:
            raise ValueError("chunker made no progress")
        chunk_text = text[start:end]
        chunks.append(
            {
                "text_start": start,
                "text_end": end,
                "leading_overlap_chars": max(
                    0, previous_end - start
                ),
                "text": chunk_text,
            }
        )
        if end == len(text):
            break
        previous_end = end
        start = end - overlap_chars
    return chunks


def section_title_for_offset(text: str, offset: int) -> str:
    current = ""
    cursor = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if is_heading(stripped) and cursor <= offset:
            current = stripped
        cursor += len(line)
        if cursor > offset:
            break
    return current


def build_page_chunks(
    *,
    doc_id: str,
    page_record: dict,
    min_chars: int = MIN_CHUNK_CHARS,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> list[dict]:
    text = page_record["clean_text"]
    chunks = split_page_text(
        text,
        min_chars=min_chars,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
    )
    output = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_text = str(chunk["text"])
        text_hash = sha256_text(chunk_text)
        page_number = int(page_record["page_number"])
        output.append(
            {
                "chunk_id": (
                    f"{doc_id}_p{page_number:03d}_c{index:02d}_"
                    f"{text_hash[:12]}"
                ),
                "doc_id": doc_id,
                "page_number": page_number,
                "page_start": page_number,
                "page_end": page_number,
                "chunk_index_on_page": index,
                "text_start": int(chunk["text_start"]),
                "text_end": int(chunk["text_end"]),
                "leading_overlap_chars": int(
                    chunk["leading_overlap_chars"]
                ),
                "char_count": len(chunk_text),
                "non_whitespace_char_count": len(
                    re.sub(r"\s+", "", chunk_text)
                ),
                "section_title": section_title_for_offset(
                    text, int(chunk["text_start"])
                ),
                "text": chunk_text,
                "text_hash": text_hash,
                "page_text_hash": page_record["text_hash"],
            }
        )
    return output
