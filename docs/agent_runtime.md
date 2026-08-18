# Agent Runtime Contract

The public runtime is a bounded single-Agent research service. Its default mode
is `MOCK_ONLY`: it uses deterministic routing and ten strict local tools over
`data/demo_synthetic/`. It performs no network request, reads no API key, and
cannot execute arbitrary shell commands or arbitrary file paths.

The optional online adapter follows the OpenAI Responses API and Function calling
model. Tool arguments use strict Structured Outputs-compatible JSON
schemas. The Agents SDK adapter is disabled in the default service and requires
separate explicit authorization and credentials before any online execution.

The runtime enforces:

- an allowlist of synthetic fund codes and report periods;
- at most six tool steps per request;
- numeric claims recalculated from registered CSV files;
- citations checked against registered chunks and source hashes;
- refusal before tool use for advice, guarantees, fabrication, secret access,
  command execution, prompt injection, and tool-budget abuse;
- redacted local traces that omit the query, answer, and evidence text.

The evaluation design follows the principle to Evaluate agent workflows with
fixed cases, deterministic tools, explicit expected routes, and machine-readable
checks. Passing the offline suite validates routing and software controls only;
it does not validate real-model reasoning or language quality.
