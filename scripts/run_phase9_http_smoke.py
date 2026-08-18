from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 8000
BASE_URL = f"http://{HOST}:{PORT}"
RESULT_PATH = PROJECT_ROOT / "results/v2_agent/phase9/http_smoke.json"


def request_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None
    request_headers = headers or {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {**request_headers, "Content-Type": "application/json"}
    request = urllib.request.Request(
        BASE_URL + path, data=body, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> int:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fund_agent_v2.api:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ready: tuple[int, dict[str, Any]] | None = None
        for _ in range(40):
            try:
                ready = request_json("/health/ready")
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.25)
        if ready is None:
            raise RuntimeError("service did not become ready")
        research = request_json(
            "/v1/research",
            method="POST",
            payload={"query": "002980的净值指标是什么？"},
            headers={"X-Request-ID": "phase9-http-001"},
        )
        online = request_json(
            "/v1/research",
            method="POST",
            payload={"query": "当前研究范围支持哪些基金？"},
            headers={"X-Run-Mode": "online"},
        )
        metrics = urllib.request.urlopen(BASE_URL + "/metrics", timeout=5).read()
        output = {
            "health_status": ready[1]["status"],
            "registered_data_files": len(ready[1]["data_checks"]),
            "research_http_status": research[0],
            "research_status": research[1]["status"],
            "request_id": research[1]["request_id"],
            "model_calls": research[1]["usage"]["model_calls"],
            "network_requests": research[1]["usage"]["network_requests"],
            "online_mode_http_status": online[0],
            "online_mode_reason": online[1]["reason_codes"],
            "metrics_has_counter": b"fund_agent_requests_total" in metrics,
        }
        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(output, ensure_ascii=False))
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
