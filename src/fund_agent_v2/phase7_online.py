from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from agents import Runner

from .phase6 import atomic_write_json
from .phase7_io import DEFAULT_PHASE7_CONFIG, load_phase7_config
from .phase7_schemas import OnlineAgentDraft
from .sdk_adapter import (
    FundSdkContext,
    assert_online_execution_authorized,
    build_sdk_agent,
    build_sdk_run_config,
)
from .tools import WORKSPACE_ROOT, build_toolbox

ONLINE_OUTPUT_ROOT = WORKSPACE_ROOT / "results/v2_agent/phase7_online"
API_SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact(value: str) -> str:
    return API_SECRET_PATTERN.sub("[REDACTED_API_KEY]", value)


def _usage_snapshot(result: Any) -> dict[str, int | None]:
    response = getattr(result, "_last_processed_response", None)
    usage = getattr(response, "usage", None)
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def run_online_canary(
    *,
    query: str = "当前研究范围支持哪些基金和报告期？",
    request_id: str = "phase7-online-canary-001",
    explicit_authorization: bool = True,
    config_path: Path = DEFAULT_PHASE7_CONFIG,
    show_answer: bool = False,
) -> dict[str, Any]:
    """Run exactly one authorized online request and write only a redacted audit."""
    started = time.perf_counter()
    config = load_phase7_config(config_path)
    assert_online_execution_authorized(
        explicit_authorization=explicit_authorization
    )
    agent = build_sdk_agent(config)
    context = FundSdkContext(toolbox=build_toolbox(), request_id=request_id)
    try:
        result = Runner.run_sync(
            agent,
            query,
            context=context,
            max_turns=config.max_tool_steps,
            run_config=build_sdk_run_config(config),
        )
        draft = result.final_output_as(OnlineAgentDraft, raise_if_incorrect_type=True)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        output: dict[str, Any] = {
            "phase": "PHASE_7_ONLINE_CANARY",
            "status": draft.status,
            "request_id": request_id,
            "query_sha256": _sha256_text(query),
            "answer_sha256": _sha256_text(draft.answer),
            "reason_codes": draft.reason_codes,
            "citation_count": len(draft.citations),
            "numeric_claim_count": len(draft.numeric_claims),
            "model": config.model,
            "tool_steps": None,
            "elapsed_ms": elapsed_ms,
            "usage": _usage_snapshot(result),
            "estimated_cost_usd": None,
            "network_requests": 1,
            "model_calls": 1,
            "redaction": "QUERY_AND_ANSWER_OMITTED",
        }
        if show_answer:
            output["answer"] = draft.answer
        atomic_write_json(ONLINE_OUTPUT_ROOT / "canary_result.json", output)
        return output
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        output = {
            "phase": "PHASE_7_ONLINE_CANARY",
            "status": "ERROR",
            "request_id": request_id,
            "query_sha256": _sha256_text(query),
            "error_type": type(exc).__name__,
            "error_message": _redact(str(exc)),
            "elapsed_ms": elapsed_ms,
            "network_requests": 1,
            "model_calls": 1,
            "redaction": "QUERY_AND_ANSWER_OMITTED",
        }
        atomic_write_json(ONLINE_OUTPUT_ROOT / "canary_error.json", output)
        raise RuntimeError(
            f"online canary failed: {type(exc).__name__}: {_redact(str(exc))}"
        ) from exc
