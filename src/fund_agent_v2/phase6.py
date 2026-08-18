from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .errors import ToolError, ToolErrorCode
from .repository import load_phase6_config, sha256_file
from .schemas import (
    BuildEvidenceTableInput,
    CalculateNavMetricsInput,
    CompareFundsInput,
    CompareHoldingsInput,
    EvidenceClaimInput,
    ExportResearchMemoInput,
    FetchOfficialSourceInput,
    LoadFundProfileInput,
    NumericClaimInput,
    RetrieveReportEvidenceInput,
    ValidateNumericClaimsInput,
    VerifyCitationsInput,
)
from .tools import DEFAULT_PHASE6_CONFIG, WORKSPACE_ROOT, build_toolbox

PROTECTED_V1_HASHES = {
    "src/metrics.py": (
        "3d356d450bf3ba28ddc9395e65f4adc15d0964c10c5eedfae9642feeaa619b19"
    ),
    "src/retrieval.py": (
        "96219315e3131117e667225ca270e46b5d0f2cbb512958b9ca8f863df0dd4fdf"
    ),
    "src/memo.py": (
        "16e0840613c14e95038e7fad1fbb4da22f0d361ba8d4d1e9c9af4a30dc984be2"
    ),
}

TOOL_CONTRACTS = {
    "load_fund_profile": ("LoadFundProfileInput", "FundProfileOutput"),
    "calculate_nav_metrics": ("CalculateNavMetricsInput", "NavMetricsOutput"),
    "compare_holdings": ("CompareHoldingsInput", "HoldingsComparisonOutput"),
    "retrieve_report_evidence": (
        "RetrieveReportEvidenceInput",
        "RetrievalOutput",
    ),
    "fetch_official_source": ("FetchOfficialSourceInput", "OfficialSourceOutput"),
    "verify_citations": ("VerifyCitationsInput", "CitationVerificationOutput"),
    "compare_funds": ("CompareFundsInput", "FundComparisonOutput"),
    "build_evidence_table": ("BuildEvidenceTableInput", "EvidenceTableOutput"),
    "validate_numeric_claims": (
        "ValidateNumericClaimsInput",
        "NumericValidationOutput",
    ),
    "export_research_memo": (
        "ExportResearchMemoInput",
        "ExportResearchMemoOutput",
    ),
}


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    _atomic_write(path, (payload + "\n").encode("utf-8"))


def atomic_write_text(path: Path, value: str) -> None:
    _atomic_write(path, value.encode("utf-8"))


def _report(summary: dict[str, Any]) -> str:
    return f"""# Phase 6 基金 Agent 确定性工具层报告

## 阶段结论

Phase 6 已实现十个受限确定性工具。工具层可以读取预注册基金资料、重算净值指标、比较公开前十大持仓、执行离线 TF-IDF 检索、核对本地官方来源 manifest、验证引用与数字，并在人工批准后导出 Markdown Memo。本阶段没有接入 LLM、OpenAI API、真实网络或付费服务。

## 数据与研究边界

- 数据配置：`demo_synthetic`，包含 3 只虚构基金和 4 个合成报告期。
- NAV 样本共同窗口：{summary["nav"]["common_start_date"]} 至 {summary["nav"]["common_end_date"]}，共 {summary["nav"]["common_observations"]} 个观测。
- 文档内容、基金代码、净值、持仓和 URL 均为确定性生成的合成数据。
- 核心确定性计算源码与注册合成数据均以 SHA-256 校验。
- 旧 F7 holdout 状态为 `FROZEN_DO_NOT_READ`，本阶段未读取、未运行、未用于设计。

## 工具与权限

十个工具均使用 `extra=forbid` 与 strict Pydantic schema；调用由统一运行时执行 allowlist、超时、错误分类和脱敏审计。工具输入不包含路径、Shell、环境变量或密钥字段。`fetch_official_source` 的结果模式为 `{summary["official_source"]["cache_mode"]}`，网络请求数为 {summary["official_source"]["network_request_count"]}。

正式导出具有双重约束：文件名必须通过安全格式校验，目标目录固定在 V2 输出根；同时必须提供人工批准、审批人和审批编号。冒烟测试中的未批准导出结果为 `{summary["export_denial"]}`。

## 数值一致性

净值收益、年化波动率和最大回撤均从 `nav_daily.csv` 的共同日期窗口重算；C10、HHI10、NameJaccard 与 CommonNAVShare 均从同报告期的公开前十大持仓重算。数值验证工具不接受调用方提供的参考结果，而是回查注册数据。冒烟测试数值验证为 `all_valid={summary["numeric"]["all_valid"]}`。

## 引用与检索

检索保留 V1 中文字符 2-4 gram TF-IDF 确定性基线。检索结果按基金和报告期强制过滤，并标记为不可信内容。引用验证同时核对 URL、doc_id、基金、报告期、物理页、chunk、文本哈希、页面哈希与 PDF 哈希。冒烟测试引用验证为 `all_valid={summary["citation"]["all_valid"]}`。

证据表只确认“引用可定位且摘录为原文精确子串”，不会把文本相关性包装成语义蕴含或因果证明。PDF 或网页内出现的提示词被视为普通不可信数据，不能改变权限。

## 审计与错误

本次冒烟流程共产生 {summary["audit"]["event_count"]} 条审计事件，其中 {summary["audit"]["success_count"]} 条成功、{summary["audit"]["expected_error_count"]} 条预期拒绝。审计只保存请求 ID、工具名、时间、耗时、状态以及输入/输出 SHA-256，不保存查询原文、证据全文或密钥。

错误分为 `INVALID_INPUT`、`POLICY_VIOLATION`、`NOT_FOUND`、`DATA_INTEGRITY`、`TIMEOUT`、`APPROVAL_REQUIRED` 与 `INTERNAL_ERROR`。Phase 6 仅把超时标为可重试。

## 限制与下一阶段 Gate

- 本阶段不是 Agent，只是 Agent 将来可调用的确定性工具层。
- 本阶段没有真实网页抓取；所谓官方来源获取只是本地 manifest/cache 定位。
- 本阶段没有语义模型、Embedding、BM25、reranker 或自动 Judge。
- 合成样本只能验证软件契约，不能证明真实基金研究质量。
- 未产生新的 holdout 结果，也没有 post-freeze forward 证据。

只有用户明确批准 Phase 7 后，才可根据当前官方文档核对 API、接入单 Agent，并创建新的开发与对抗评测。真实 API 调用仍需另行显式授权。
"""


def run_phase6(config_path: Path = DEFAULT_PHASE6_CONFIG) -> dict[str, Any]:
    config = load_phase6_config(config_path)
    toolbox = build_toolbox(config_path=config_path)
    profile = toolbox.load_fund_profile(
        LoadFundProfileInput(profile="demo_synthetic"), request_id="p6-profile"
    )
    nav = toolbox.calculate_nav_metrics(
        CalculateNavMetricsInput(fund_codes=config.allowed_fund_codes),
        request_id="p6-nav",
    )
    holdings = toolbox.compare_holdings(
        CompareHoldingsInput(
            fund_code_a="SYN002", fund_code_b="SYN001", period="2026Q1"
        ),
        request_id="p6-holdings",
    )
    retrieval = toolbox.retrieve_report_evidence(
        RetrieveReportEvidenceInput(
            query="市场震荡和分散配置",
            fund_codes=["SYN001"],
            periods=["2026Q1"],
            top_k=3,
        ),
        request_id="p6-retrieval",
    )
    if not retrieval.cards:
        raise RuntimeError("Phase 6 smoke retrieval returned no evidence")
    card = retrieval.cards[0]
    official = toolbox.fetch_official_source(
        FetchOfficialSourceInput(url=card.citation.announcement_url),
        request_id="p6-official",
    )
    citation = toolbox.verify_citations(
        VerifyCitationsInput(citations=[card.citation]),
        request_id="p6-citation",
    )
    comparison = toolbox.compare_funds(
        CompareFundsInput(fund_code_a="SYN002", fund_code_b="SYN001", period="2026Q2"),
        request_id="p6-comparison",
    )
    evidence_claims = [
        EvidenceClaimInput(
            claim_id="p6-evidence-1",
            claim_text="合成报告提及市场震荡和分散配置。",
            evidence_excerpt=card.evidence_text[:12],
            citation=card.citation,
        )
    ]
    evidence = toolbox.build_evidence_table(
        BuildEvidenceTableInput(claims=evidence_claims),
        request_id="p6-evidence",
    )
    nav_by_code = {row.fund_code: row for row in nav.metrics}
    numeric_claims = [
        NumericClaimInput(
            claim_id="p6-number-1",
            metric="cumulative_change",
            claimed_value=nav_by_code["SYN001"].cumulative_change,
            fund_code="SYN001",
        ),
        NumericClaimInput(
            claim_id="p6-number-2",
            metric="common_nav_share",
            claimed_value=holdings.common_nav_share,
            fund_code="SYN002",
            comparison_fund_code="SYN001",
            period="2026Q1",
        ),
    ]
    numeric = toolbox.validate_numeric_claims(
        ValidateNumericClaimsInput(claims=numeric_claims),
        request_id="p6-numeric",
    )
    export_denial = "NOT_RUN"
    try:
        toolbox.export_research_memo(
            ExportResearchMemoInput(
                file_name="phase6_unapproved_memo.md",
                title="不应导出的 Memo",
                markdown_body="此调用用于验证人工审批 Gate。",
                evidence_claims=evidence_claims,
                numeric_claims=numeric_claims,
                human_approved=False,
                approved_by="phase6-smoke",
                approval_id="phase6_denial_001",
            ),
            request_id="p6-export-denied",
        )
    except ToolError as exc:
        if exc.code != ToolErrorCode.APPROVAL_REQUIRED:
            raise
        export_denial = exc.code.value

    events = toolbox.audit_sink.events()
    summary: dict[str, Any] = {
        "phase": "PHASE_6",
        "profile": {
            "fund_codes": profile.fund_codes,
            "periods": profile.periods,
            "dataset_version": profile.dataset_version,
        },
        "nav": {
            "common_start_date": nav.common_start_date.isoformat(),
            "common_end_date": nav.common_end_date.isoformat(),
            "common_observations": nav.common_observations,
            "metrics": [row.model_dump(mode="json") for row in nav.metrics],
        },
        "holdings": holdings.model_dump(mode="json"),
        "retrieval": {
            "model_version": retrieval.model_version,
            "result_count": retrieval.result_count,
            "top_chunk_id": card.citation.chunk_id,
            "top_score": card.score,
            "untrusted_content": card.untrusted_content,
        },
        "official_source": official.model_dump(mode="json"),
        "citation": citation.model_dump(mode="json"),
        "comparison": {
            "fund_code_a": comparison.fund_code_a,
            "fund_code_b": comparison.fund_code_b,
            "period": comparison.period,
            "cumulative_change_difference_a_minus_b": (
                comparison.cumulative_change_difference_a_minus_b
            ),
        },
        "evidence": evidence.model_dump(mode="json"),
        "numeric": numeric.model_dump(mode="json"),
        "export_denial": export_denial,
        "audit": {
            "event_count": len(events),
            "success_count": sum(event.status == "SUCCESS" for event in events),
            "expected_error_count": sum(event.status == "ERROR" for event in events),
        },
        "network_request_count": 0,
        "llm_call_count": 0,
        "old_holdout_read_count": 0,
    }

    output_root = WORKSPACE_ROOT / config.outputs["root"]
    report_path = WORKSPACE_ROOT / config.outputs["report"]
    contracts = {
        name: {
            "input_schema": models[0],
            "output_schema": models[1],
            "timeout_seconds": config.tool_timeouts_seconds[name],
        }
        for name, models in TOOL_CONTRACTS.items()
    }
    atomic_write_json(output_root / "tool_contracts.json", contracts)
    atomic_write_json(output_root / "smoke_results.json", summary)
    audit_payload = "".join(
        event.model_dump_json(exclude_none=False) + "\n" for event in events
    )
    atomic_write_text(output_root / "audit_events.jsonl", audit_payload)
    atomic_write_text(report_path, _report(summary))

    source_names = (
        "audit.py",
        "calculations.py",
        "errors.py",
        "phase6.py",
        "phase6_gate.py",
        "policy.py",
        "repository.py",
        "retrieval_engine.py",
        "schemas.py",
        "tools.py",
    )
    sources = [
        WORKSPACE_ROOT / "src/fund_agent_v2" / name
        for name in source_names
    ]
    scripts = [
        WORKSPACE_ROOT / "scripts/run_phase6.py",
        WORKSPACE_ROOT / "scripts/run_phase6_gate.py",
    ]
    outputs = [
        output_root / "tool_contracts.json",
        output_root / "smoke_results.json",
        output_root / "audit_events.jsonl",
        report_path,
    ]
    manifest = {
        "phase": "PHASE_6",
        "config": {
            str(config_path.relative_to(WORKSPACE_ROOT)).replace(
                "\\", "/"
            ): sha256_file(config_path)
        },
        "protected_v1": PROTECTED_V1_HASHES,
        "registered_data": {
            f"{config.dataset_root}/{name}": expected
            for name, expected in config.file_sha256.items()
        },
        "source_hashes": {
            str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/"): sha256_file(path)
            for path in [*sources, *scripts]
        },
        "outputs": {
            str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/"): sha256_file(path)
            for path in outputs
        },
        "old_holdout_policy": "FROZEN_DO_NOT_READ",
        "old_holdout_read_count": 0,
        "network_request_count": 0,
        "llm_call_count": 0,
        "protected_core_files_modified": False,
    }
    atomic_write_json(output_root / "run_manifest.json", manifest)
    return summary
