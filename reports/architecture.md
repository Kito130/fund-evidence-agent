# Architecture

## Problem Boundary

The service answers bounded research questions from registered local artifacts.
It deliberately separates deterministic numeric analysis from evidence-backed
text answers and from refusal decisions. A missing report page is not silently
treated as a zero, a forecast, or a complete holding list.

## Components

```text
data/demo_synthetic/
  profile + NAV + top-10 + industry + source manifest
  chunks + deterministic TF-IDF index
          |
          +--> src/metrics.py / dashboard.py
          |       NAV and public-holdings diagnostics
          |
          +--> src/retrieval.py / memo.py
          |       scoped lexical retrieval and evidence Memo
          |
          +--> fund_agent_v2/repository.py
          |       registered files, hashes, and schemas
          |
          +--> fund_agent_v2/tools.py
          |       ten deterministic allowlisted tools
          |
          +--> fund_agent_v2/single_agent.py
          |       bounded state machine and refusal policy
          |
          +--> fund_agent_v2/api.py
                  FastAPI, health, metrics, request IDs, degradation
```

## Data Contracts

The public registry uses three synthetic fund codes, four report periods, and a
reserved `.invalid` source domain. Each tool receives a strict Pydantic input
model and returns a strict output contract. Fund code and period filters are
mandatory for evidence retrieval. The repository verifies registered file
hashes before the service reports readiness.

## Agent Runtime

The default `MOCK_ONLY` runtime is a deterministic single-Agent state machine.
It has a maximum of six tool steps, no arbitrary shell or filesystem access,
and no network or secret access. It can:

- load a fund profile;
- calculate NAV metrics;
- compare public top-10 holdings;
- retrieve and verify report evidence;
- compare funds and build evidence tables;
- validate numeric claims;
- export a Memo only after a separate approval contract.

Before tool use, policy checks reject investment advice, guarantees, fabricated
evidence, secret/file/command requests, prompt injection, and tool-budget abuse.
Answered text carries citations; numeric outputs are recalculated from
registered CSV files. Redacted traces retain request IDs, tool names, timings,
statuses, and hashes, but omit query, answer, and evidence text.

## Service and Deployment

`fund_agent_v2.api` exposes `/health/live`, `/health/ready`, `/metrics`, and
`POST /v1/research`. Readiness checks the registered synthetic file hashes.
Docker runs as a non-root user with a read-only synthetic-data bind mount,
dropped capabilities, a read-only filesystem, and a loopback host binding in
Compose. This is a local research service boundary, not a production
investment-advice deployment.

## Optional Online Boundary

The OpenAI/Agents SDK adapter is kept optional and disabled by default. Its
configuration is a contract for a future authorized experiment, not evidence
that real API calls have been made or that model quality has been validated.
