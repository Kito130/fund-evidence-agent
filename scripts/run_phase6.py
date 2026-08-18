from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


if __name__ == "__main__":
    run_phase6 = import_module("fund_agent_v2.phase6").run_phase6
    result = run_phase6()
    print(json.dumps(result, ensure_ascii=False))
