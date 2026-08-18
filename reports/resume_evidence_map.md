# Resume Evidence Map

This map describes defensible engineering evidence from the public repository.
It is not a performance claim and should not be detached from the synthetic and
`MOCK_ONLY` labels.

## Evidence 1: Deterministic fund research platform

Claim: implemented a local fund research surface for NAV risk metrics, public
top-10 concentration/overlap, industry allocation, and bounded document
retrieval.

- Source modules: `src/metrics.py`, `src/dashboard.py`, `src/retrieval.py`,
  `src/memo.py`;
- Public data: `data/demo_synthetic/` with three synthetic funds and four report
  periods;
- Contract tests: `tests/test_public_demo.py`, `tests/test_metrics.py`,
  `tests/test_retrieval.py`;
- Boundary: public top-10 is not complete portfolio exposure; synthetic files
  are not real fund evidence.

## Evidence 2: Evidence-constrained single-Agent runtime

Claim: implemented a deterministic single-Agent baseline with strict tool
schemas, allowlisted routing, citation checks, numeric re-computation, refusal,
prompt-injection blocking, and redacted traces.

- Source modules: `src/fund_agent_v2/single_agent.py`, `tools.py`,
  `guardrails.py`, `repository.py`, `api.py`;
- Runtime controls: ten tools, six-step maximum, `MOCK_ONLY`, zero network and
  zero model calls;
- Evaluation: 32 fixed cases across seven named suites, 32/32 on the current
  synthetic corpus;
- Boundary: this is deterministic software evaluation, not real LLM quality.

## Evidence 3: Local service packaging

Claim: packaged the runtime as a local FastAPI/Docker service with readiness
checks, request IDs, metrics, read-only synthetic data, non-root execution, and
safe online-mode rejection.

- Source: `src/fund_agent_v2/api.py`, `Dockerfile`, `compose.yaml`;
- Endpoints: `/health/live`, `/health/ready`, `/metrics`, `/v1/research`;
- Boundary: no hosted deployment or investment-advice functionality.

Every statement above should link to the relevant source file and state that the
public data profile is synthetic and the Agent evaluation mode is `MOCK_ONLY`.
