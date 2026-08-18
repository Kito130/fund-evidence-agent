from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .guardrails import classify_request
from .phase6 import atomic_write_json, atomic_write_text
from .phase7_io import (
    DEFAULT_PHASE7_CONFIG,
    configured_eval_paths,
    load_eval_cases,
    load_phase7_config,
)
from .phase7_schemas import EvalCase, EvalCaseResult, EvalSummary
from .repository import sha256_file
from .single_agent import DeterministicMockSingleAgent
from .tools import WORKSPACE_ROOT, build_toolbox

OFFLINE_CASE_LATENCY_LIMIT_MS = 2_000.0
PHASE6_MANIFEST = (
    WORKSPACE_ROOT / "results/v2_agent/phase6/run_manifest.json"
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/")


def _jsonl(models: list[EvalCaseResult]) -> str:
    return "".join(model.model_dump_json() + "\n" for model in models)


def _evaluate_case(
    case: EvalCase,
    *,
    agent: DeterministicMockSingleAgent,
) -> tuple[EvalCaseResult, dict[str, Any]]:
    response = agent.run(case.query, request_id=f"phase7-{case.case_id}")
    config = agent.config
    decision = classify_request(
        case.query,
        allowed_funds=set(config.allowed_fund_codes),
        allowed_periods=set(config.allowed_periods),
        max_input_chars=config.max_input_chars,
    )
    actual_tools = [step.tool_name for step in response.tool_steps]
    status_correct = response.status == case.expected_status
    tool_route_correct = actual_tools == case.expected_tools
    decision_scope_correct = (
        decision.fund_codes == case.expected_fund_codes
        and decision.periods == case.expected_periods
    )
    step_funds = sorted(
        {fund for step in response.tool_steps for fund in step.fund_codes}
    )
    step_periods = sorted(
        {period for step in response.tool_steps for period in step.periods}
    )
    step_scope_correct = not case.expected_tools or (
        step_funds == case.expected_fund_codes
        and step_periods == case.expected_periods
    )
    scope_arguments_correct = decision_scope_correct and step_scope_correct
    reason_correct = set(case.expected_reason_codes).issubset(response.reason_codes)
    numeric_valid = not case.require_numeric_validation or bool(
        response.numeric_checks
        and all(check.valid for check in response.numeric_checks)
    )
    citations_valid = not case.require_citation_validation or bool(
        response.citations
        and response.evidence_rows
        and all(
            row.citation_valid
            and row.exact_excerpt
            and row.status == "LOCATED"
            for row in response.evidence_rows
        )
    )
    budget_respected = len(response.tool_steps) <= config.max_tool_steps
    latency_ok = response.usage.elapsed_ms <= OFFLINE_CASE_LATENCY_LIMIT_MS
    usage_zero = (
        response.usage.model_calls == 0
        and response.usage.network_requests == 0
        and response.usage.input_tokens == 0
        and response.usage.output_tokens == 0
        and response.usage.estimated_cost_usd == 0.0
    )
    checks = {
        "STATUS": status_correct,
        "TOOL_ROUTE": tool_route_correct,
        "SCOPE_ARGUMENTS": scope_arguments_correct,
        "REASON": reason_correct,
        "NUMERIC": numeric_valid,
        "CITATION": citations_valid,
        "TOOL_BUDGET": budget_respected,
        "LATENCY": latency_ok,
        "ZERO_USAGE": usage_zero,
    }
    failure_reasons = [name for name, passed in checks.items() if not passed]
    result = EvalCaseResult(
        case_id=case.case_id,
        suite=case.suite,
        passed=not failure_reasons,
        status_correct=status_correct,
        tool_route_correct=tool_route_correct,
        scope_arguments_correct=scope_arguments_correct,
        reason_correct=reason_correct,
        numeric_valid=numeric_valid,
        citations_valid=citations_valid,
        budget_respected=budget_respected,
        latency_ms=response.usage.elapsed_ms,
        tool_steps=len(response.tool_steps),
        cost_usd=response.usage.estimated_cost_usd,
        failure_reasons=failure_reasons,
    )
    trace = {
        "case_id": case.case_id,
        "suite": case.suite,
        "request_id": response.request_id,
        "query_sha256": _sha256_text(case.query),
        "answer_sha256": _sha256_text(response.answer),
        "status": response.status,
        "reason_codes": response.reason_codes,
        "tools": [step.model_dump(mode="json") for step in response.tool_steps],
        "usage": response.usage.model_dump(mode="json"),
        "redaction": "QUERY_ANSWER_AND_EVIDENCE_OMITTED",
    }
    return result, trace


def evaluate_cases(
    cases: list[EvalCase],
    *,
    agent: DeterministicMockSingleAgent,
) -> tuple[list[EvalCaseResult], list[dict[str, Any]], EvalSummary]:
    results: list[EvalCaseResult] = []
    traces: list[dict[str, Any]] = []
    for case in cases:
        result, trace = _evaluate_case(case, agent=agent)
        results.append(result)
        traces.append(trace)

    by_suite: dict[str, list[EvalCaseResult]] = defaultdict(list)
    for result in results:
        by_suite[result.suite].append(result)
    suite_metrics = {
        suite: {
            "total": len(rows),
            "passed": sum(row.passed for row in rows),
            "pass_rate": sum(row.passed for row in rows) / len(rows),
        }
        for suite, rows in sorted(by_suite.items())
    }
    total = len(results)
    passed = sum(result.passed for result in results)
    summary = EvalSummary(
        phase="PHASE_7_OFFLINE",
        execution_mode="MOCK_ONLY",
        total_cases=total,
        passed_cases=passed,
        pass_rate=passed / total if total else 0.0,
        suite_metrics=suite_metrics,
        average_tool_steps=(
            sum(result.tool_steps for result in results) / total if total else 0.0
        ),
        average_latency_ms=(
            sum(result.latency_ms for result in results) / total if total else 0.0
        ),
        total_model_calls=0,
        total_network_requests=0,
        total_cost_usd=0.0,
        old_holdout_read_count=0,
        new_holdout_open_count=0,
        online_evaluation_status="NOT_RUN_REQUIRES_EXPLICIT_AUTHORIZATION",
    )
    return results, traces, summary


def _report(summary: EvalSummary, results: list[EvalCaseResult]) -> str:
    suite_lines = [
        "| 评测集 | 通过 | 总数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for suite, metrics in summary.suite_metrics.items():
        suite_lines.append(
            f"| {suite} | {metrics['passed']} | {metrics['total']} | "
            f"{float(metrics['pass_rate']):.1%} |"
        )
    failures = [result.case_id for result in results if not result.passed]
    failure_text = "、".join(failures) if failures else "无"
    return f"""# Phase 7 单 Agent 离线评测报告

## 阶段结论

本阶段在 Phase 6 十个确定性工具之上实现了一个单 Agent，并使用全新 V2 题集执行确定性 mock 评测。共 {summary.total_cases} 个用例，通过 {summary.passed_cases} 个，通过率 {summary.pass_rate:.1%}。失败用例：{failure_text}。

这不是大模型质量评测。mock 运行只证明状态机、工具路由、参数范围、数字回算、引用定位、拒答策略、提示注入防御以及审计链能够在离线条件下按冻结规则工作，不能证明真实模型的语言质量或泛化能力。

## 分组结果

{chr(10).join(suite_lines)}

## 安全与证据边界

- 单次最多 {6} 个工具步骤；离线单例延迟门槛为 {OFFLINE_CASE_LATENCY_LIMIT_MS:.0f} ms。
- 数值回答必须经过 `validate_numeric_claims` 回查注册数据。
- 文档回答必须依次完成检索、引用完整性验证和原文精确定位。
- 个性化投资建议、未来收益保证、伪造证据、密钥/文件/命令请求、工具预算滥用和 Prompt Injection 均在调用工具前拒绝。
- 本地 trace 已脱敏，不保存原始问题、回答或证据全文。
- 正式 Memo 导出仍需外部人工审批，本阶段没有导出。

## 成本、网络与 Holdout

- 模型调用：{summary.total_model_calls}
- 网络请求：{summary.total_network_requests}
- Token：0
- 估算成本：USD {summary.total_cost_usd:.2f}
- 旧 F7 holdout 读取次数：{summary.old_holdout_read_count}
- 新 final holdout 打开次数：{summary.new_holdout_open_count}

所有题目均为全新 V2 development/adversarial 工程评测题。旧 F7 development 与 holdout 没有读取、复制或运行；本阶段也没有创建 final holdout。

## 在线 Gate

候选在线配置已冻结为 Responses API、官方 Python Agents SDK、`gpt-5.6-terra`、`reasoning.effort=medium`、`text.verbosity=medium`、`store=false`、串行工具调用和 SDK tracing 关闭。真实 API 评测尚未运行，必须同时满足用户单独明确授权和环境变量 `OPENAI_API_KEY`，并继续遵守 USD 1.00 单请求成本上限。
"""


def run_phase7_offline(
    config_path: Path = DEFAULT_PHASE7_CONFIG,
) -> dict[str, Any]:
    config = load_phase7_config(config_path)
    cases = load_eval_cases(config)
    agent = DeterministicMockSingleAgent(config=config, toolbox=build_toolbox())
    results, traces, summary = evaluate_cases(cases, agent=agent)

    output_root = WORKSPACE_ROOT / config.outputs["root"]
    report_path = WORKSPACE_ROOT / config.outputs["report"]
    results_path = output_root / "case_results.jsonl"
    traces_path = output_root / "redacted_traces.jsonl"
    summary_path = output_root / "evaluation_summary.json"
    atomic_write_text(results_path, _jsonl(results))
    atomic_write_text(
        traces_path,
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in traces),
    )
    atomic_write_json(summary_path, summary.model_dump(mode="json"))
    atomic_write_text(report_path, _report(summary, results))

    phase6_manifest = json.loads(PHASE6_MANIFEST.read_text(encoding="utf-8"))
    source_paths = sorted(
        path
        for path in (WORKSPACE_ROOT / "src/fund_agent_v2").glob("*.py")
        if path.name.startswith("phase7_")
        or path.name in {"guardrails.py", "sdk_adapter.py", "single_agent.py"}
    )
    script_paths = sorted(
        (WORKSPACE_ROOT / "scripts").glob("run_phase7*.py")
    )
    test_paths = sorted(
        (WORKSPACE_ROOT / "tests").glob("test_phase7*.py")
    )
    frozen_inputs = [
        config_path,
        WORKSPACE_ROOT / "docs/agent_runtime.md",
        WORKSPACE_ROOT / "docs/evaluation_protocol.md",
        WORKSPACE_ROOT / "prompts/fund_agent_v1.md",
        WORKSPACE_ROOT / "pyproject.toml",
        *configured_eval_paths(config).values(),
    ]
    outputs = [results_path, traces_path, summary_path, report_path]
    manifest = {
        "phase": "PHASE_7_OFFLINE",
        "execution_mode": "MOCK_ONLY",
        "random_seed": config.random_seed,
        "case_count": len(cases),
        "frozen_inputs": {
            _relative(path): sha256_file(path) for path in sorted(frozen_inputs)
        },
        "source_hashes": {
            _relative(path): sha256_file(path)
            for path in [*source_paths, *script_paths, *test_paths]
        },
        "outputs": {_relative(path): sha256_file(path) for path in outputs},
        "phase6_manifest_sha256": sha256_file(PHASE6_MANIFEST),
        "phase6_protected": {
            **phase6_manifest["protected_v1"],
            **phase6_manifest["registered_data"],
            **phase6_manifest["config"],
            **phase6_manifest["outputs"],
            **phase6_manifest["source_hashes"],
        },
        "old_holdout_policy": "FROZEN_DO_NOT_READ",
        "old_holdout_read_count": 0,
        "old_development_read_count": 0,
        "new_holdout_status": "NOT_CREATED",
        "new_holdout_open_count": 0,
        "model_call_count": 0,
        "network_request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "formal_export_count": 0,
        "online_evaluation_status": "NOT_RUN_REQUIRES_EXPLICIT_AUTHORIZATION",
    }
    atomic_write_json(output_root / "run_manifest.json", manifest)
    return summary.model_dump(mode="json")
