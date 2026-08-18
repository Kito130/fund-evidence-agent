from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from typing import Annotated, Any

from fastapi import FastAPI, Header, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import Field

from .phase7_io import load_phase7_config
from .phase7_schemas import AgentResponse
from .schemas import StrictModel
from .single_agent import DeterministicMockSingleAgent
from .tools import build_toolbox

LOGGER = logging.getLogger("fund_agent_v2.api")
APP_VERSION = "0.1.0"


class ResearchRequest(StrictModel):
    query: Annotated[str, Field(min_length=1, max_length=1000)]


class DegradedResponse(StrictModel):
    request_id: str
    status: str = "DEGRADED"
    reason_codes: list[str] = Field(default_factory=lambda: ["SERVICE_DEGRADED"])


class ServiceMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters = {
            "requests_total": 0,
            "answered_total": 0,
            "refused_total": 0,
            "agent_errors_total": 0,
            "degraded_total": 0,
            "tool_steps_total": 0,
            "model_calls_total": 0,
            "network_requests_total": 0,
        }
        self._latency_ms_total = 0.0

    def record(self, response: AgentResponse) -> None:
        with self._lock:
            self._counters["requests_total"] += 1
            self._counters["tool_steps_total"] += len(response.tool_steps)
            self._counters["model_calls_total"] += response.usage.model_calls
            self._counters["network_requests_total"] += response.usage.network_requests
            self._latency_ms_total += response.usage.elapsed_ms
            if response.status == "ANSWERED":
                self._counters["answered_total"] += 1
            elif response.status == "REFUSED":
                self._counters["refused_total"] += 1
            else:
                self._counters["agent_errors_total"] += 1

    def record_degraded(self) -> None:
        with self._lock:
            self._counters["degraded_total"] += 1

    def prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP fund_agent_requests_total Bounded research requests.",
                "# TYPE fund_agent_requests_total counter",
                f"fund_agent_requests_total {self._counters['requests_total']}",
                "# HELP fund_agent_model_calls_total Model calls; zero in mock mode.",
                "# TYPE fund_agent_model_calls_total counter",
                f"fund_agent_model_calls_total {self._counters['model_calls_total']}",
                "# HELP fund_agent_network_requests_total External requests; zero in mock mode.",
                "# TYPE fund_agent_network_requests_total counter",
                (
                    "fund_agent_network_requests_total "
                    f"{self._counters['network_requests_total']}"
                ),
                "# HELP fund_agent_tool_steps_total Deterministic tool steps.",
                "# TYPE fund_agent_tool_steps_total counter",
                f"fund_agent_tool_steps_total {self._counters['tool_steps_total']}",
                "# HELP fund_agent_latency_ms_total End-to-end mock agent latency.",
                "# TYPE fund_agent_latency_ms_total counter",
                f"fund_agent_latency_ms_total {self._latency_ms_total:.6f}",
            ]
            return "\n".join(lines) + "\n"


class FundAgentService:
    def __init__(self) -> None:
        self.config = load_phase7_config()
        self.toolbox = build_toolbox()
        self.agent = DeterministicMockSingleAgent(
            config=self.config, toolbox=self.toolbox
        )
        self.metrics = ServiceMetrics()

    @staticmethod
    def _log(event: str, **fields: Any) -> None:
        LOGGER.info(json.dumps({"event": event, **fields}, ensure_ascii=False))

    def readiness(self) -> tuple[bool, dict[str, bool]]:
        checks = self.toolbox.repository.verify_all_registered_hashes()
        return all(checks.values()), checks

    def research(self, query: str, *, request_id: str) -> AgentResponse:
        response = self.agent.run(query, request_id=request_id)
        self.metrics.record(response)
        self._log(
            "research_completed",
            request_id=request_id,
            query_sha256=hashlib.sha256(query.encode("utf-8")).hexdigest(),
            status=response.status,
            reason_codes=response.reason_codes,
            tool_steps=len(response.tool_steps),
            elapsed_ms=round(response.usage.elapsed_ms, 3),
            model_calls=response.usage.model_calls,
            network_requests=response.usage.network_requests,
            estimated_cost_usd=response.usage.estimated_cost_usd,
        )
        return response


service = FundAgentService()
app = FastAPI(
    title="Fund Agent V2",
    version=APP_VERSION,
    description="Evidence-constrained local mock research service.",
)


def _request_id(header_value: str | None) -> str:
    return header_value or uuid.uuid4().hex


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok", "mode": service.config.execution_mode, "version": APP_VERSION}


@app.get("/health/ready")
def readiness() -> JSONResponse:
    try:
        ready, checks = service.readiness()
    except Exception as exc:  # noqa: BLE001 - readiness must fail closed
        service.metrics.record_degraded()
        FundAgentService._log("readiness_failed", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "data_checks": {}},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ok" if ready else "degraded", "data_checks": checks},
    )


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return service.metrics.prometheus()


@app.post("/v1/research", response_model=AgentResponse)
def research(
    payload: ResearchRequest,
    response: Response,
    x_request_id: Annotated[str | None, Header()] = None,
    x_run_mode: Annotated[str | None, Header()] = None,
) -> AgentResponse | JSONResponse:
    request_id = _request_id(x_request_id)
    response.headers["X-Request-ID"] = request_id
    if x_run_mode is not None and x_run_mode.lower() != "mock":
        service.metrics.record_degraded()
        FundAgentService._log(
            "online_mode_rejected", request_id=request_id, requested_mode=x_run_mode
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=DegradedResponse(
                request_id=request_id, reason_codes=["ONLINE_MODE_DISABLED"]
            ).model_dump(),
        )
    try:
        return service.research(payload.query, request_id=request_id)
    except Exception as exc:  # noqa: BLE001 - request failures degrade safely
        service.metrics.record_degraded()
        FundAgentService._log(
            "research_degraded", request_id=request_id, error_type=type(exc).__name__
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=DegradedResponse(request_id=request_id).model_dump(),
        )
