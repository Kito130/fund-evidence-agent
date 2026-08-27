# Offline Evaluation Protocol

The public evaluation uses 32 fixed cases across development, adversarial,
tool-selection, numeric-consistency, citation-integrity, refusal, and
prompt-injection suites. All in-scope entities are synthetic (`SYN001` through
`SYN003`) and all tools read only registered files under
`data/demo_synthetic/`.

Each case checks response status, ordered tool route, detected fund and period
scope, reason codes, tool-step budget, numeric validation, and citation
validation where applicable. The run manifest records hashes of the config,
case files, source files, registered tool-contract manifest, and generated
outputs.

Evidence answers also require the top deterministic retrieval score to meet the
frozen `0.31` threshold. This corpus-specific threshold rejects low-relevance
matches; it is not a calibrated semantic-confidence probability.

The evaluation must report zero model calls, zero network requests, zero tokens,
and zero API cost. Queries and answers are omitted from redacted traces. A pass
therefore demonstrates deterministic software behavior and safety controls; it
must not be described as evidence of real LLM quality, production readiness, or
investment performance.
