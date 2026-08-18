from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one authorized Phase 7 API canary")
    parser.add_argument("--query", default="当前研究范围支持哪些基金和报告期？")
    parser.add_argument("--show-answer", action="store_true")
    args = parser.parse_args()
    run_online_canary = import_module(
        "fund_agent_v2.phase7_online"
    ).run_online_canary
    result = run_online_canary(query=args.query, show_answer=args.show_answer)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
