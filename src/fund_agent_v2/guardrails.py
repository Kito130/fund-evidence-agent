from __future__ import annotations

import re
from typing import Literal

from .phase7_schemas import ScopeDecision
from .retrieval_engine import detect_injection_signals

FUND_CODE_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:SYN[0-9]{3}|[0-9]{6})(?![A-Z0-9])",
    re.IGNORECASE,
)
PERIOD_PATTERN = re.compile(r"(?<![0-9])[0-9]{4}Q[1-4](?![0-9])", re.IGNORECASE)
SECURITY_PATTERN = re.compile(
    r"api[ _-]?key|密钥|凭证|环境变量|\.env|读取.{0,8}(文件|目录)|"
    r"shell|powershell|cmd\.exe|subprocess|执行.{0,8}(命令|脚本)",
    re.IGNORECASE,
)
ADVICE_PATTERN = re.compile(
    r"替我买|应该买|个性化投资建议|适合我的投资|all[ -]?in", re.IGNORECASE
)
GUARANTEE_PATTERN = re.compile(r"保证.{0,6}(收益|赚钱)|稳赚|未来收益保证|一定上涨")
FORGERY_PATTERN = re.compile(r"伪造.{0,8}(引用|页码|来源|数字)|编造.{0,8}(引用|证据)")
EXHAUSTION_PATTERN = re.compile(
    r"([0-9]{2,}|一千|无限).{0,8}(次|遍).{0,8}(工具|调用|检索)|"
    r"(工具|调用|检索).{0,8}([0-9]{2,}|一千|无限).{0,8}(次|遍)"
)


def classify_request(
    query: str,
    *,
    allowed_funds: set[str],
    allowed_periods: set[str],
    max_input_chars: int,
) -> ScopeDecision:
    codes = sorted({value.upper() for value in FUND_CODE_PATTERN.findall(query)})
    periods = sorted({value.upper() for value in PERIOD_PATTERN.findall(query)})
    reasons: list[str] = []
    if len(query) > max_input_chars:
        reasons.append("INPUT_TOO_LONG")
    if detect_injection_signals(query):
        reasons.append("PROMPT_INJECTION")
    if SECURITY_PATTERN.search(query):
        reasons.append("SECRET_FILE_OR_COMMAND_REQUEST")
    if ADVICE_PATTERN.search(query):
        reasons.append("PERSONALIZED_INVESTMENT_ADVICE")
    if GUARANTEE_PATTERN.search(query):
        reasons.append("FUTURE_RETURN_GUARANTEE")
    if FORGERY_PATTERN.search(query):
        reasons.append("FABRICATED_EVIDENCE_REQUEST")
    if EXHAUSTION_PATTERN.search(query):
        reasons.append("TOOL_BUDGET_ABUSE")
    if set(codes) - allowed_funds:
        reasons.append("FUND_OUT_OF_SCOPE")
    if set(periods) - allowed_periods:
        reasons.append("PERIOD_OUT_OF_SCOPE")
    if reasons:
        return ScopeDecision(
            allowed=False,
            intent="NONE",
            reason_codes=sorted(set(reasons)),
            fund_codes=[code for code in codes if code in allowed_funds],
            periods=[period for period in periods if period in allowed_periods],
        )

    intent: Literal["PROFILE", "NAV", "HOLDINGS", "EVIDENCE", "COMPARE", "NONE"]
    if any(
        term in query for term in ("支持哪些基金", "研究范围", "数据范围", "基金列表")
    ):
        intent = "PROFILE"
    elif (
        len(codes) >= 2
        and len(periods) == 1
        and any(term in query for term in ("持仓", "重合", "jaccard", "C10", "HHI"))
    ):
        intent = "HOLDINGS"
    elif (
        len(codes) >= 2
        and len(periods) == 1
        and any(term in query for term in ("比较", "对比", "差异"))
    ):
        intent = "COMPARE"
    elif codes and any(
        term in query
        for term in ("累计收益", "收益率", "年化波动", "最大回撤", "净值指标")
    ):
        intent = "NAV"
    elif (
        codes
        and periods
        and any(
            term in query
            for term in (
                "报告",
                "原文",
                "证据",
                "投资方向",
                "人工智能",
                "半导体",
                "基金经理学历",
            )
        )
    ):
        intent = "EVIDENCE"
    else:
        intent = "NONE"
        reasons.append("UNSUPPORTED_QUESTION")
    return ScopeDecision(
        allowed=intent != "NONE",
        intent=intent,
        reason_codes=reasons or ["IN_SCOPE"],
        fund_codes=codes,
        periods=periods,
    )
