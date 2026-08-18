from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


if __name__ == "__main__":
    run_phase7_offline = import_module("fund_agent_v2.phase7_eval").run_phase7_offline
    result = run_phase7_offline()
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["pass_rate"] == 1.0 else 1)
