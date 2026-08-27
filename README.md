# Fund Evidence Agent

这是一个证据约束型基金研究 Agent：它对净值和公开前十大持仓进行确定性计算，从已
登记的报告片段中检索证据，并在引用不足、数字无法复算或请求越界时拒答。公开版本
使用完全合成数据和确定性 `MOCK_ONLY` 路由，用于验证工程契约，不代表真实 LLM 质量。
[中文完整说明](README.zh-CN.md)

Fund disclosures are incomplete, heterogeneous, and easy to overinterpret.
This project separates deterministic calculations, document evidence, and
refusal decisions so that an answer can be traced to a registered table,
bounded excerpt, validation result, or explicit reason for not answering.

## At a Glance

| Surface | What is implemented | Public evidence |
| --- | --- | --- |
| Fund analytics | NAV return/volatility/drawdown, top-10 concentration and overlap, industry changes | Three synthetic funds across four report periods |
| Retrieval | Chinese character 2-4 gram TF-IDF with fund, period, score, page, and hash checks | Registered synthetic chunks and deterministic index |
| Agent runtime | Intent routing, ten allowlisted tools, strict schemas, numeric/citation validation, refusal | 32 fixed offline cases across seven suites |
| Service | FastAPI, request IDs, health/readiness, metrics, safe degradation | Local Docker service bound to loopback |

## Research Boundary

The default public runtime uses only `SYN001`, `SYN002`, and `SYN003` with
invented NAV, holdings, report text, hashes, and `.invalid` URLs. It makes zero
model calls and zero network requests and requires no API key. This baseline
tests tool and evidence contracts; it does not establish real-model reasoning,
semantic retrieval quality, live fund facts, investment advice, or production
readiness. Data classifications are listed in
[data/DATA_MANIFEST.md](data/DATA_MANIFEST.md).

## System Design

```text
registered synthetic files
        |
        +--> deterministic fund metrics
        |
        +--> scoped TF-IDF retrieval --> page, chunk, and hash validation
                                      |
                                      v
                         bounded Agent state machine
                                      |
                         ANSWERED / REFUSED / DEGRADED
                                      |
                       FastAPI + redacted audit metrics
```

The runtime permits at most six tool steps. Before tool execution, it rejects
personalized investment advice, return guarantees, fabricated evidence,
secret/file/command requests, prompt injection, and tool-budget abuse. Numeric
claims are recalculated from registered CSV files. Evidence answers must pass
scope, retrieval-score, page, chunk, and source-hash checks. Redacted traces
retain request IDs, tool names, status, duration, and hashes while omitting the
query, answer, and evidence text.

The retrieval threshold `0.31` is a corpus-specific lexical relevance gate,
not a calibrated confidence probability. Public top-10 metrics describe only
the disclosed rows and never stand in for complete portfolio exposure.

Detailed design: [reports/architecture.md](reports/architecture.md). Runtime
contract: [docs/agent_runtime.md](docs/agent_runtime.md).

## Verified API Example

Request to `POST /v1/research`:

```json
{"query":"请计算SYN001的净值指标。"}
```

Bounded response fields:

```json
{
  "status": "ANSWERED",
  "answer": "SYN001 累计收益 0.094260，年化波动 0.061029，最大回撤 -0.066125",
  "reason_codes": ["NUMERICALLY_VERIFIED"],
  "usage": {
    "model_calls": 0,
    "network_requests": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "estimated_cost_usd": 0.0
  }
}
```

Unsupported or unsafe requests return `REFUSED` with machine-readable reason
codes instead of an unsupported narrative.

## Offline Evaluation

| Suite | Cases | Focus |
| --- | ---: | --- |
| adversarial | 4 | out-of-scope and hostile requests |
| citation integrity | 4 | page, chunk, hash, and scope validation |
| development | 5 | expected answer routes and schemas |
| numeric consistency | 4 | recalculation of numeric claims |
| prompt injection | 5 | blocking before tool execution |
| refusal | 5 | evidence and policy boundaries |
| tool selection | 5 | ordered allowlisted tool routes |
| **Total** | **32** | **32/32 on this deterministic corpus** |

The run records zero model calls, network requests, tokens, and API cost. It
also records zero reads of the old holdout and does not create a new final
holdout. These results validate the listed software controls only; see
[reports/evaluation.md](reports/evaluation.md) for the exact interpretation.

## Run Locally

```powershell
python -m pip install -e ".[dev]"
python scripts/run_pipeline.py --profile demo_synthetic
python -m pytest -q
```

The pipeline checks one supported answer and one evidence refusal, printing
`network_calls=0` and `api_keys_required=0`.

Start the API:

```powershell
$env:FUND_AGENT_MODE = "MOCK_ONLY"
python -m uvicorn fund_agent_v2.api:app --app-dir src --host 127.0.0.1 --port 8000
```

Endpoints: `/health/live`, `/health/ready`, `/metrics`, and
`POST /v1/research`.

Run the containerized service:

```powershell
docker compose up --build --wait
python scripts/run_container_smoke.py
docker compose down
```

The container uses a non-root user, a read-only filesystem and synthetic-data
mount, dropped Linux capabilities, and a loopback host binding.

## Repository Guide

```text
src/                 deterministic analytics and Agent runtime
configs/             runtime, tool, and evaluation contracts
data/demo_synthetic/ reproducible synthetic registry and tables
eval/                 fixed deterministic evaluation cases
tests/                analytics, safety, API, and runtime contracts
scripts/              preparation, evaluation, and service entry points
reports/              architecture, evaluation, limitations, and demo guide
compose.yaml          local loopback service definition
```

## Limits

- Character n-gram TF-IDF is lexical retrieval, not semantic RAG.
- The small fixed corpus does not establish arbitrary-question generalization.
- Public top-10 holdings cannot reveal complete exposures or portfolio overlap.
- The optional online adapter is disabled and has not undergone a real LLM
  quality evaluation in this public release.
- The service provides no live data, forecasts, trading signals, personalized
  advice, or hosted deployment.

Data rights: [DATA_LICENSE.md](DATA_LICENSE.md). Detailed limitations:
[reports/limitations.md](reports/limitations.md). Original source code is
released under the [MIT License](LICENSE); that license does not cover fund
documents, market data, provider responses, or trademarks. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
