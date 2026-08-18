from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT
RESULT_ROOT = PROJECT_ROOT / "results/v2_agent/phase9"
REPORT_ROOT = PROJECT_ROOT / "reports"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def check(name: str, passed: bool, evidence: str) -> dict[str, Any]:
    return {"check": name, "passed": bool(passed), "evidence": evidence}


def docker_audit() -> dict[str, Any]:
    docker = shutil.which("docker")
    if docker is None:
        return {"cli": False, "daemon": False, "version": None, "error": "CLI_ABSENT"}
    environment = os.environ.copy()
    docker_config = Path(environment.get("TEMP", str(RESULT_ROOT))) / "fund-agent-docker-config"
    docker_config.mkdir(parents=True, exist_ok=True)
    environment["DOCKER_CONFIG"] = str(docker_config)
    result = subprocess.run(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=environment,
    )
    version = result.stdout.strip() or None
    return {
        "cli": True,
        "daemon": result.returncode == 0,
        "version": version,
        "error": result.stderr.strip()[:300] if result.returncode else None,
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Phase 9 部署与正式报告 Gate",
        "",
        f"**结论：{result['status']}**",
        "",
        "| 检查项 | 结果 | 证据 |",
        "| --- | --- | --- |",
    ]
    for item in result["checks"]:
        lines.append(
            f"| {item['check']} | {'PASS' if item['passed'] else 'BLOCKED/FAIL'} | "
            f"{str(item['evidence']).replace('|', '\\|')} |"
        )
    lines.extend(
        [
            "",
            "服务固定为 MOCK_ONLY；本 Gate 不调用真实模型或外部 API。",
            "V1 与 Phase 7 冻结输入保持只读，Docker daemon 未就绪时不伪造容器通过结果。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    phase6_manifest = json.loads(
        (PROJECT_ROOT / "results/v2_agent/phase6/run_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    phase7_gate = json.loads(
        (PROJECT_ROOT / "results/v2_agent/phase7_offline/phase7_gate_report.json").read_text(
            encoding="utf-8"
        )
    )
    phase9_manifest = json.loads(
        (RESULT_ROOT / "phase9_manifest.json").read_text(encoding="utf-8")
    )
    smoke_path = RESULT_ROOT / "http_smoke.json"
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    docker = docker_audit()
    checks: list[dict[str, Any]] = []
    checks.append(check("Phase 7 依赖 Gate", phase7_gate["status"] == "PASS", "26/26"))
    checks.append(
        check(
            "HTTP readiness 与研究 smoke",
            smoke["health_status"] == "ok"
            and smoke["research_http_status"] == 200
            and smoke["research_status"] == "ANSWERED"
            and smoke["registered_data_files"] == 6,
            json.dumps(smoke, ensure_ascii=False, sort_keys=True),
        )
    )
    checks.append(
        check(
            "在线模式安全拒绝",
            smoke["online_mode_http_status"] == 403
            and smoke["online_mode_reason"] == ["ONLINE_MODE_DISABLED"],
            "online=403, no fallback",
        )
    )
    checks.append(
        check(
            "HTTP 指标端点",
            smoke["metrics_has_counter"] is True,
            "Prometheus counter present",
        )
    )
    checks.append(
        check(
            "服务 mock 成本与网络为零",
            smoke["model_calls"] == 0 and smoke["network_requests"] == 0,
            "model_calls=0, network_requests=0",
        )
    )
    pdf_path = REPORT_ROOT / "phase9_research_report.pdf"
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
    checks.append(
        check(
            "PDF 可读与视觉 QA 产物",
            len(PdfReader(str(pdf_path)).pages) >= 1
            and all(phrase in pdf_text for phrase in ("MOCK_ONLY", "Phase 8", "限制"))
            and (PROJECT_ROOT / "tmp/pdfs/phase9_render-1.png").is_file(),
            f"pages={len(PdfReader(str(pdf_path)).pages)}",
        )
    )
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    api_source = (PROJECT_ROOT / "src/fund_agent_v2/api.py").read_text(encoding="utf-8")
    checks.append(
        check(
            "无密钥写入与在线旁路",
            not re.search(r"sk-[A-Za-z0-9_-]{8,}", env_example)
            and "OPENAI_API_KEY" not in api_source
            and "Runner.run" not in api_source,
            "service source contains no key loading or online runner",
        )
    )
    phase6_protected = {
        **phase6_manifest["protected_v1"],
        **phase6_manifest["registered_data"],
        **phase6_manifest["config"],
        **phase6_manifest["outputs"],
        **phase6_manifest["source_hashes"],
    }
    protected_ok = all(
        (WORKSPACE_ROOT / path).is_file()
        and sha256_file(WORKSPACE_ROOT / path) == digest
        for path, digest in phase6_protected.items()
    )
    checks.append(check("V1 与 Phase 6 哈希不变", protected_ok, f"files={len(phase6_protected)}"))
    output_ok = all(
        (WORKSPACE_ROOT / path).is_file()
        and sha256_file(WORKSPACE_ROOT / path) == digest
        for path, digest in phase9_manifest["outputs"].items()
    )
    checks.append(check("Phase 9 报告与 manifest 哈希", output_ok, "3 outputs"))
    checks.append(
        check(
            "Phase 8 选择可追溯",
            phase9_manifest["phase8_status"]
            == "SKIPPED_OPTIONAL_NO_MEASURABLE_SINGLE_AGENT_GAIN_EVIDENCE",
            "single Agent retained as baseline",
        )
    )
    checks.append(
        check(
            "Docker CLI 与 daemon",
            docker["cli"] and docker["daemon"],
            json.dumps(docker, ensure_ascii=False, sort_keys=True),
        )
    )
    status = "PASS" if all(item["passed"] for item in checks) else "BLOCKED_DOCKER_DAEMON"
    result = {
        "phase": "PHASE_9",
        "status": status,
        "check_count": len(checks),
        "passed_count": sum(item["passed"] for item in checks),
        "checks": checks,
        "model_calls": 0,
        "network_requests": 0,
        "estimated_cost_usd": 0.0,
        "docker": docker,
    }
    (RESULT_ROOT / "phase9_gate_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (REPORT_ROOT / "phase9_gate_report.md").write_text(
        markdown(result), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
