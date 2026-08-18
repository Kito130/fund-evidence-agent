# Evaluation

## Protocol

The public V2 evaluation is deterministic and uses only the registered
synthetic dataset. It contains 32 fixed cases across seven named suites:

| Suite | Cases | Contract focus |
| --- | ---: | --- |
| adversarial | 4 | unsafe or unsupported request handling |
| citation_integrity | 4 | page, chunk, hash, and scope validation |
| development | 5 | normal routing and answer schemas |
| numeric_consistency | 4 | recalculation of numeric claims |
| prompt_injection | 5 | tool-free blocking of hostile instructions |
| refusal | 5 | evidence insufficiency and policy refusal |
| tool_selection | 5 | expected ordered tool route |
| **Total** | **32** | **deterministic mock evaluation** |

The fixed threshold `0.31` is a corpus-specific top retrieval score gate. It is
not a calibrated confidence score. Each case also checks detected fund/period
scope, reason codes, tool-step budget, and redacted audit output where relevant.

## Result

The current machine-readable evaluation reports 32/32 cases passed for this
exact synthetic corpus. The named suite counts above are the scope of that
number; it is not a claim that every user question will pass.

The run records:

```text
model calls:       0
network requests:  0
tokens:            0
estimated cost:    USD 0.00
old holdout reads: 0
new final holdout: not created
```

The result validates deterministic routing, strict schemas, numeric checks,
citations, refusal, prompt-injection blocking, and audit controls. It does not
validate real LLM reasoning, language quality, semantic retrieval,
generalization, or production readiness.

## Reproduction

```powershell
python scripts/run_phase7_offline.py
python scripts/run_phase7_gate.py
python -m pytest -q
```

The public pipeline is the smaller end-to-end path:

```powershell
python scripts/run_pipeline.py --profile demo_synthetic
```

Historical Phase 6/7/9 files remain as evidence artifacts only. The public
navigation is this document, [architecture.md](architecture.md), and the
runtime contract in [../docs/agent_runtime.md](../docs/agent_runtime.md).
