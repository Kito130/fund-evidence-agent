"""Create one local F6 template Memo or the fixed refusal response."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.memo import (  # noqa: E402
    MAX_MEMO_CARDS,
    REFUSAL_MESSAGE,
    retrieve_and_build_memo,
)
from src.retrieval import validate_index  # noqa: E402


DEFAULT_CHUNKS = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
DEFAULT_INDEX = (
    PROJECT_ROOT / "data" / "processed" / "tfidf_index.json"
)
DEFAULT_F5_AUDIT = PROJECT_ROOT / "results" / "f5_audit.json"
DEFAULT_MARKDOWN = (
    PROJECT_ROOT / "data" / "processed" / "query_memo.md"
)
DEFAULT_JSON = (
    PROJECT_ROOT / "data" / "processed" / "query_memo.json"
)


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


def validate_f5_gate(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("stage") != "F5" or payload.get("status") != "PASS":
        raise ValueError("F5 must pass before creating an F6 Memo")
    model = payload.get("model", {})
    if "idf_values" in model or "vectors" in model:
        raise ValueError("tracked F5 audit contains private index data")


def validate_selected_values(
    *,
    chunks: list[dict],
    fund_codes: list[str],
    periods: list[str],
) -> None:
    available_funds = {str(chunk["fund_code"]) for chunk in chunks}
    available_periods = {str(chunk["period"]) for chunk in chunks}
    unknown_funds = set(fund_codes) - available_funds
    unknown_periods = set(periods) - available_periods
    if unknown_funds:
        raise ValueError(
            f"unknown fund_code filter: {sorted(unknown_funds)}"
        )
    if unknown_periods:
        raise ValueError(
            f"unknown period filter: {sorted(unknown_periods)}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--fund-code", action="append", required=True)
    parser.add_argument("--period", action="append", required=True)
    parser.add_argument(
        "--top-k",
        type=int,
        choices=range(1, MAX_MEMO_CARDS + 1),
        default=MAX_MEMO_CARDS,
    )
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--f5-audit", type=Path, default=DEFAULT_F5_AUDIT)
    parser.add_argument(
        "--markdown-output", type=Path, default=DEFAULT_MARKDOWN
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_f5_gate(args.f5_audit.resolve())
    chunks = read_jsonl(args.chunks.resolve())
    index = json.loads(args.index.resolve().read_text(encoding="utf-8"))
    validate_index(index, chunks)
    validate_selected_values(
        chunks=chunks,
        fund_codes=args.fund_code,
        periods=args.period,
    )
    memo = retrieve_and_build_memo(
        args.query,
        index=index,
        chunks=chunks,
        fund_codes=args.fund_code,
        periods=args.period,
        top_k=args.top_k,
    )
    markdown_path = args.markdown_output.resolve()
    json_path = args.json_output.resolve()
    markdown = memo["markdown"]
    if not markdown.endswith("\n"):
        markdown += "\n"
    atomic_write_text(markdown_path, markdown)
    atomic_write_text(
        json_path,
        json.dumps(
            memo,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    if memo["status"] == "REFUSED":
        print(REFUSAL_MESSAGE)
    else:
        print(
            f"F6 ANSWERED: {len(memo['citations'])} supported "
            "citation(s)"
        )
        for citation in memo["citations"]:
            print(
                f"doc={citation['doc_id']} "
                f"physical_page={citation['physical_page']} "
                f"chunk_id={citation['chunk_id']}"
            )
    print(
        "Memo content saved only to ignored local files: "
        f"{markdown_path}; {json_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
