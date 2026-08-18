"""Run the public offline demo pipeline without network or API keys."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.dashboard import (  # noqa: E402
    DEFAULT_PROFILE,
    load_dashboard_data,
    load_research_engine,
    research_scope,
    run_research_query,
    validate_dashboard_data,
)
from src.memo import REFUSAL_MESSAGE  # noqa: E402


PUBLIC_PROFILES = ("demo_synthetic",)

PROFILE_QUERIES = {
    "demo_synthetic": "市场保持震荡",
}


def parse_args(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=PUBLIC_PROFILES,
        default=DEFAULT_PROFILE,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = load_dashboard_data(
        PROJECT_ROOT,
        profile=args.profile,
    )
    counts = validate_dashboard_data(bundle)
    index, chunks = load_research_engine(
        PROJECT_ROOT,
        profile=args.profile,
    )
    funds, periods = research_scope(chunks)
    fund_code = sorted(funds)[0]
    period = sorted(periods)[-1]
    answered = run_research_query(
        PROFILE_QUERIES[args.profile],
        fund_code=fund_code,
        period=period,
        top_k=3,
        index=index,
        chunks=chunks,
    )
    refused = run_research_query(
        "请提供火星基地明天的天气和彩票号码。",
        fund_code=fund_code,
        period=period,
        top_k=3,
        index=index,
        chunks=chunks,
    )
    if answered["memo"]["status"] != "ANSWERED":
        raise ValueError("public demo answer case did not pass")
    if (
        refused["memo"]["status"] != "REFUSED"
        or refused["memo"]["markdown"] != REFUSAL_MESSAGE
    ):
        raise ValueError("public demo refusal case did not pass")

    print(f"profile={args.profile}")
    print(f"fund_count={counts['fund_count']}")
    print(f"report_count={counts['report_count']}")
    print(f"nav_rows={counts['nav_rows']}")
    print(f"chunk_count={len(chunks)}")
    print("answer_case=PASS")
    print("refusal_case=PASS")
    print("network_calls=0")
    print("api_keys_required=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
