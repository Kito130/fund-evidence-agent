from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("FUND_AGENT_BASE_URL", "http://127.0.0.1:8000")


def request_json(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def request_text(path: str) -> tuple[int, str]:
    with urlopen(f"{BASE_URL}{path}", timeout=10) as response:
        return response.status, response.read().decode("utf-8")


def main() -> int:
    live_status, live = request_json("GET", "/health/live")
    ready_status, ready = request_json("GET", "/health/ready")
    research_status, research = request_json(
        "POST",
        "/v1/research",
        payload={"query": "002980的净值指标是什么？"},
        headers={"X-Request-ID": "container-smoke-001"},
    )
    online_status, online = request_json(
        "POST",
        "/v1/research",
        payload={"query": "当前研究范围支持哪些基金？"},
        headers={"X-Run-Mode": "online"},
    )
    metrics_status, metrics = request_text("/metrics")

    checks = {
        "live": live_status == 200 and live.get("status") == "ok",
        "mock_only": live.get("mode") == "MOCK_ONLY",
        "ready": ready_status == 200
        and ready.get("status") == "ok"
        and all(ready.get("data_checks", {}).values()),
        "research": research_status == 200
        and research.get("status") == "ANSWERED",
        "zero_model_calls": research.get("usage", {}).get("model_calls") == 0,
        "zero_network_requests": (
            research.get("usage", {}).get("network_requests") == 0
        ),
        "online_rejected": online_status == 403
        and online.get("reason_codes") == ["ONLINE_MODE_DISABLED"],
        "metrics": metrics_status == 200
        and "fund_agent_model_calls_total 0" in metrics
        and "fund_agent_network_requests_total 0" in metrics,
    }
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "base_url": BASE_URL,
        "checks": checks,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
