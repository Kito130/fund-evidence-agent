from __future__ import annotations

import hashlib
import json
import os
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT / "src"))
atomic_write_json = import_module("fund_agent_v2.phase6").atomic_write_json
atomic_write_text = import_module("fund_agent_v2.phase6").atomic_write_text

REPORT_DIR = PROJECT_ROOT / "reports"
RESULT_DIR = PROJECT_ROOT / "results/v2_agent/phase9"
PDF_PATH = REPORT_DIR / "phase9_research_report.pdf"
MD_PATH = REPORT_DIR / "phase9_research_report.md"
MAP_PATH = REPORT_DIR / "phase9_resume_evidence_map.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(WORKSPACE_ROOT).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def markdown(phase7: dict[str, Any], gate: dict[str, Any]) -> str:
    passed = phase7["passed_cases"]
    total = phase7["total_cases"]
    return f"""# Phase 9 基金 Agent V2 本地部署与正式研究报告

## 1. 执行结论

本阶段把 Phase 6 的确定性基金工具和 Phase 7 的单 Agent mock 状态机封装为一个本地 FastAPI 服务，并加入健康检查、请求 ID、结构化脱敏日志、Prometheus 风格指标和安全降级。服务默认 `MOCK_ONLY`，不会访问真实 OpenAI API，也不会读取 API Key。

Phase 7 离线评测通过 {passed}/{total}，通过率 {phase7['pass_rate']:.1%}；Phase 7 离线 Gate 为 `{gate['status']}`（{gate['passed_count']}/{gate['check_count']}）。本报告的数字来自机器可读结果，不是大模型自报。

## 2. 研究问题与岗位相关性

研究对象是证据可追溯的公募基金诊断平台：在受限基金和报告期范围内回答净值指标、公开前十大持仓重合和报告原文证据问题。它展示量化研究员岗位需要的数值回算、数据边界、拒答机制、可观察性和可部署工程能力。

## 3. 部署架构

```text
HTTP client
  -> FastAPI typed service
  -> request-id and scope boundary
  -> DeterministicMockSingleAgent
  -> ten Phase 6 deterministic tools
  -> numeric/citation validation
  -> AgentResponse or safe refusal
  -> redacted logs and metrics
```

FastAPI 在这里解决健康检查、可编程调用、结构化日志和运行指标问题；没有同时堆叠 Streamlit、React 或队列系统。Docker 只使用仓库内的 `data/demo_synthetic`，该目录可通过只读 volume 挂载。

## 4. 数据与时间边界

- 数据 profile：`demo_synthetic`，三只虚构基金、四个合成报告期。
- NAV 和持仓数据沿用 Phase 6 已注册、哈希锁定的数据。
- 这些结果属于 `HISTORICAL_RESEARCH` / `SECONDARY_EVALUATION`，不是新的 untouched OOS。
- 旧 F7 development/holdout 未读取，新 final holdout 未创建。
- 服务 readiness 会重新校验全部注册文件 SHA-256；失败时返回 503。

## 5. 安全与失败降级

- `X-Run-Mode: online` 直接返回 403 `ONLINE_MODE_DISABLED`。
- 服务不暴露路径、Shell、环境变量、密钥或任意 URL 工具。
- Agent 状态机只允许最多 6 个工具步骤，证据不足、范围越界、注入和建议请求安全拒绝。
- 初始化、数据完整性或运行时异常返回 503 `DEGRADED`，不会切换到外部模型。
- 日志只保存 request ID、问题 SHA-256、状态、原因、工具数、耗时和 usage；不保存原文、答案全文或证据全文。

## 6. 机器评测

| 项目 | 结果 |
| --- | ---: |
| Phase 7 V2 cases | {total} |
| 通过 | {passed} |
| 通过率 | {phase7['pass_rate']:.1%} |
| 模型调用 | 0 |
| 网络请求 | 0 |
| 估算成本 | USD 0.00 |
| Phase 7 Gate | {gate['status']} |

评测包含 development、adversarial、tool selection、numeric consistency、citation integrity、refusal 和 prompt injection 七组。所有正式数字先由确定性工具计算，再由验证工具回查。

## 7. Phase 8 决策

Phase 8 多 Agent 是可选项，要求在同一题集、同一工具预算、同一成本约束下证明可测增益。当前只有 mock 工程评测，没有真实模型质量证据，因此不实现多 Agent，保留单 Agent 作为基线，避免为简历堆叠没有增益的复杂度。

## 8. 失败结果与限制

- mock 评测不能证明真实模型的语言质量、泛化或实际 API 成本。
- 合成样本只能验证软件契约，不代表任何真实基金历史或持仓。
- 公开前十大持仓不等于完整组合；证据定位不等于因果证明。
- 服务只适合本地研究工作台，不是公网生产系统；未启用认证、TLS 或多租户隔离。
- Phase 9 不产生新的投资建议，也不保证未来收益。

## 9. 复现命令

```powershell
python -m pytest -q
python -m ruff check src scripts tests
$env:PYTHONPATH = "src"
python -m mypy src tests
python scripts\\run_phase7_offline.py
python scripts\\run_phase7_gate.py
```

本地服务启动：

```powershell
python -m uvicorn fund_agent_v2.api:app --host 127.0.0.1 --port 8000
```

## 10. 证据映射

公开工程结论及其边界见 `reports/architecture.md` 和
`reports/evaluation.md`；机器结果保留在 `results/v2_agent/` 的合成评测产物中。
"""


def resume_map() -> str:
    return """# Phase 9 简历证据映射

| 简历候选表述 | 机器结果 | 源码/配置 | 数据与审计 |
| --- | --- | --- | --- |
| 设计证据约束的基金研究 Agent | Phase 7 32/32 cases, 26/26 Gate | `src/fund_agent_v2/single_agent.py`, `phase7_eval.py` | `results/v2_agent/phase7_offline/evaluation_summary.json` |
| 实现十个严格 schema 工具 | SDK Gate tools=10, additionalProperties=false | `src/fund_agent_v2/sdk_adapter.py`, `schemas.py` | `results/v2_agent/phase6/tool_contracts.json` |
| 建立数值与引用双重验证链 | numeric 4/4, citation 4/4 | `tools.py`, `single_agent.py` | `case_results.jsonl`, Phase 6 manifest |
| 实现 Prompt Injection 与越界拒答 | refusal 5/5, injection 5/5, tool_steps=0 | `guardrails.py`, `retrieval_engine.py` | `redacted_traces.jsonl`, Gate report |
| 部署本地健康检查和可观察性 | `/health/live`, `/health/ready`, `/metrics`, request ID | `src/fund_agent_v2/api.py`, `compose.yaml` | Phase 9 service tests |
| 实现安全降级 | online mode 403, runtime degradation 503 | `api.py`, `.env.example` | service tests and structured logs |

使用这些数字时必须同时标注：`MOCK_ONLY`、历史/二次评测、非真实模型质量证据、非投资建议。
"""


def build_pdf(phase7: dict[str, Any], gate: dict[str, Any]) -> None:
    font_name = "STSong-Light"
    windows_root = os.environ.get("WINDIR")
    windows_font = (
        Path(windows_root) / "Fonts/msyh.ttc"
        if windows_root
        else Path("Fonts/msyh.ttc")
    )
    if windows_font.is_file():
        pdfmetrics.registerFont(
            TTFont("MicrosoftYaHei", str(windows_font), subfontIndex=0)
        )
        font_name = "MicrosoftYaHei"
    else:
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ChineseBody", parent=styles["BodyText"], fontName=font_name,
        fontSize=9.5, leading=15, spaceAfter=6,
    )
    heading = ParagraphStyle(
        "ChineseHeading", parent=body, fontSize=14, leading=20,
        spaceBefore=12, spaceAfter=8,
    )
    title = ParagraphStyle(
        "ChineseTitle", parent=body, fontSize=18, leading=26,
        alignment=TA_CENTER, spaceAfter=18,
    )
    small = ParagraphStyle("ChineseSmall", parent=body, fontSize=8, leading=11)
    document = SimpleDocTemplate(
        str(PDF_PATH), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
    )
    story: list[Any] = [
        Paragraph("Phase 9 基金 Agent V2 本地部署与正式研究报告", title),
        Paragraph("状态：MOCK_ONLY；不接入真实 API", body),
        Paragraph("1. 执行结论", heading),
        Paragraph(
            f"本阶段完成本地 FastAPI 服务、健康检查、结构化脱敏日志、指标和安全降级。Phase 7 离线评测通过 {phase7['passed_cases']}/{phase7['total_cases']}，Phase 7 Gate 为 {gate['status']}。所有数字来自机器结果。",
            body,
        ),
        Paragraph("2. 部署架构", heading),
        Paragraph("HTTP client -> FastAPI -> mock Agent -> 十个确定性工具 -> 数字/引用验证 -> 结构化回答或拒答 -> 日志与指标", body),
        Paragraph("3. 数据和边界", heading),
        Paragraph("数据为 demo_synthetic 的三只虚构基金和四个合成报告期；全部注册数据均以哈希锁定。结果只验证公开软件契约，不是投资研究 OOS。旧 F7 holdout 未读取，新 final holdout 未创建。", body),
        Paragraph("4. 安全与降级", heading),
        Paragraph("服务不读取 API Key。X-Run-Mode: online 返回 403；初始化、数据完整性或运行时异常返回 503 DEGRADED；日志不保存问题原文、答案全文、证据全文或凭证。", body),
        Paragraph("5. 机器结果", heading),
    ]
    table_data = [
        [Paragraph("指标", small), Paragraph("结果", small)],
        [Paragraph("V2 离线 cases", small), Paragraph(str(phase7["total_cases"]), small)],
        [Paragraph("通过率", small), Paragraph(f"{phase7['pass_rate']:.1%}", small)],
        [Paragraph("模型/网络/成本", small), Paragraph("0 / 0 / USD 0.00", small)],
        [Paragraph("Phase 7 Gate", small), Paragraph(gate["status"], small)],
    ]
    table = Table(table_data, colWidths=[65 * mm, 65 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#7A8A99")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([table, Spacer(1, 8)])
    story.extend([
        Paragraph("6. Phase 8 决策", heading),
        Paragraph("多 Agent 是可选阶段，必须在同一题集、预算和工具权限下证明可测增益。当前没有真实模型质量证据，因此保持单 Agent 基线，不增加没有证据支持的复杂度。", body),
        Paragraph("7. 限制", heading),
        Paragraph("mock 评测不能证明真实模型质量或真实 API 成本；合成样本不代表真实基金历史；公开前十大持仓不等于完整组合；本服务仅供本地研究工作台使用，不是公网生产系统。", body),
        Paragraph("8. 复现", heading),
        Paragraph("pytest -q；ruff check src scripts tests；mypy src tests；run_phase7_offline.py；run_phase7_gate.py。服务入口：uvicorn fund_agent_v2.api:app。", body),
    ])

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.drawString(18 * mm, 9 * mm, "Fund Agent V2 - MOCK_ONLY")
        canvas.drawRightString(192 * mm, 9 * mm, f"第 {doc.page} 页")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> int:
    phase7 = load_json(PROJECT_ROOT / "results/v2_agent/phase7_offline/evaluation_summary.json")
    gate = load_json(PROJECT_ROOT / "results/v2_agent/phase7_offline/phase7_gate_report.json")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(MD_PATH, markdown(phase7, gate))
    atomic_write_text(MAP_PATH, resume_map())
    build_pdf(phase7, gate)
    outputs = [MD_PATH, MAP_PATH, PDF_PATH]
    manifest = {
        "phase": "PHASE_9",
        "deployment_mode": "MOCK_ONLY",
        "phase8_status": "SKIPPED_OPTIONAL_NO_MEASURABLE_SINGLE_AGENT_GAIN_EVIDENCE",
        "outputs": {relative(path): sha256_file(path) for path in outputs},
        "inputs": {
            relative(PROJECT_ROOT / "results/v2_agent/phase7_offline/evaluation_summary.json"): sha256_file(PROJECT_ROOT / "results/v2_agent/phase7_offline/evaluation_summary.json"),
            relative(PROJECT_ROOT / "results/v2_agent/phase7_offline/phase7_gate_report.json"): sha256_file(PROJECT_ROOT / "results/v2_agent/phase7_offline/phase7_gate_report.json"),
        },
        "model_calls": 0,
        "network_requests": 0,
        "estimated_cost_usd": 0.0,
    }
    atomic_write_json(RESULT_DIR / "phase9_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
