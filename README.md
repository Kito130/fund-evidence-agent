# Fund Evidence Agent

An evidence-constrained fund research service for answering bounded questions
about NAV paths, public top-10 holdings, and report excerpts without silently
turning missing evidence into a claim. The repository combines the original
deterministic fund research platform with a V2 single-Agent runtime, FastAPI
service, health checks, metrics, and Docker packaging.

The default public path is deterministic and synthetic. It runs in `MOCK_ONLY`
mode, makes zero model/network calls, and requires no API key. It demonstrates
software contracts and safety controls, not real LLM quality, live fund data,
investment advice, or production readiness.

Chinese documentation: [README.zh-CN.md](README.zh-CN.md)

## Research Problem

Fund disclosures are heterogeneous and partial. The system therefore separates
three questions that are often incorrectly mixed:

1. What can be calculated deterministically from a registered NAV or public
   top-10 table?
2. Which report page and bounded excerpt support a textual answer?
3. When the local evidence is insufficient or the request is unsafe, should the
   system refuse before using a tool?

The platform computes NAV return/volatility/drawdown, public top-10
concentration, same-period top-10 overlap, and industry allocation changes. Its
retrieval baseline is Chinese character 2-4 gram TF-IDF with fund and report
period filters. The Agent runtime validates schemas, routes to an allowlisted
tool set, checks citations and numeric claims, and refuses unsupported or unsafe
requests.

## V1 Platform and V2 Agent

| Surface | What it demonstrates | Public status |
| --- | --- | --- |
| Deterministic research platform | NAV metrics, public top-10 diagnostics, bounded TF-IDF retrieval, template Memo | synthetic fixtures included |
| V2 single-Agent runtime | state-machine routing, strict tool schemas, evidence threshold, refusal and redacted traces | deterministic `MOCK_ONLY` |
| Optional online adapter | OpenAI Responses API / Agents SDK contract boundary | disabled; no real API evaluation is claimed |
| Service layer | FastAPI request IDs, health endpoints, metrics, safe degradation, Docker | local synthetic service |

The public demo uses `SYN001`, `SYN002`, and `SYN003` across four synthetic
report periods. Real fund files and complete PDFs are excluded. See
[DATA_LICENSE.md](DATA_LICENSE.md) and [data/DATA_MANIFEST.md](data/DATA_MANIFEST.md).

## Architecture

```text
synthetic registered files
        |
        +--> deterministic metrics and public-holdings diagnostics
        |
        +--> scoped TF-IDF retrieval --> evidence/citation validation
                                      |
                                      v
                         bounded single-Agent state machine
                                      |
                         ANSWERED / REFUSED / DEGRADED
                                      |
                    FastAPI + request ID + redacted audit metrics
```

The runtime has ten allowlisted tools, a six-step maximum per request, strict
Pydantic schemas, registered-file hash checks, numeric re-computation, and a
corpus-specific minimum retrieval score of `0.31`. The score is a lexical
relevance gate, not a semantic-confidence probability.

## Quick Start

### Local synthetic demo

```powershell
python -m pip install -e ".[dev]"
python scripts/run_pipeline.py --profile demo_synthetic
python -m pytest -q
```

The pipeline prints `network_calls=0` and `api_keys_required=0`, then exercises
one answer case and one evidence-refusal case. The test suite also checks that
the real-sample directory and old holdout artifacts are absent.

### FastAPI service

```powershell
$env:FUND_AGENT_MODE = "MOCK_ONLY"
python -m uvicorn fund_agent_v2.api:app --app-dir src --host 127.0.0.1 --port 8000
```

Useful endpoints are `/health/live`, `/health/ready`, `/metrics`, and
`POST /v1/research` with a JSON body such as `{"query":"SYN001 NAV"}`. The
service rejects online-mode headers and remains local-only by default.

### Docker

```powershell
docker compose up --build
```

The compose file mounts only `data/demo_synthetic` read-only, drops Linux
capabilities, uses a non-root user, and exposes the service on loopback. Docker
is a local research demonstration, not a hosted investment-advice service.

## Offline Evaluation

The V2 offline evaluation contains 32 fixed cases in seven named suites:
adversarial (4), citation integrity (4), development (5), numeric consistency
(4), prompt injection (5), refusal (5), and tool selection (5). The aggregate
result is 32/32 for this exact deterministic corpus. It checks routes, schemas,
scope, citation integrity, numeric validation, refusal, prompt-injection
blocking, and audit outputs.

The evaluation records zero model calls, zero network requests, zero tokens, and
USD 0.00 cost. Therefore it does not validate real LLM reasoning, language
quality, semantic retrieval, generalization, or production performance. See
[reports/evaluation.md](reports/evaluation.md) and
[docs/evaluation_protocol.md](docs/evaluation_protocol.md).

## Scope and Limitations

- Synthetic codes, NAV, holdings, report text, hashes, and `.invalid` URLs are
  invented and do not represent real funds or performance.
- Public top-10 metrics are not complete portfolio holdings and cannot establish
  full exposure or overlap.
- TF-IDF is lexical retrieval, not semantic RAG; the `0.31` threshold is
  corpus-specific and not a probability.
- The fixed offline corpus is small and deterministic. Passing it is not a claim
  of arbitrary-question robustness.
- The optional OpenAI adapter is disabled by default and has not been evaluated
  as real LLM quality in this public release.
- The service does not provide live prices, real-time risk, trading signals,
  return forecasts, or investment advice.

Detailed design: [reports/architecture.md](reports/architecture.md). Detailed
evaluation: [reports/evaluation.md](reports/evaluation.md). Data rights:
[DATA_LICENSE.md](DATA_LICENSE.md).

## Repository Map

```text
src/                 deterministic platform and fund_agent_v2 runtime
configs/             runtime, tool, and evaluation configuration
data/demo_synthetic/ reproducible synthetic registry and tables
eval/v2/             fixed offline evaluation cases
tests/               public contracts and runtime tests
scripts/             data preparation, evaluation, and service smoke entry points
reports/             public architecture, evaluation, limits, and historical evidence
compose.yaml         loopback Docker service
```

## License and Contributions

Original source code is released under [MIT License](LICENSE). MIT does not
license fund-company reports, market data, provider responses, excerpts,
trademarks, or other third-party material. See [DATA_LICENSE.md](DATA_LICENSE.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
