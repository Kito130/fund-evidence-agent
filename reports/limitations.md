# Limitations and Negative Findings

## Public Data Boundary

The public runtime uses only deterministic synthetic data. Real structured
tables, report excerpts, complete PDFs, downloaded pages, and private caches are
excluded. A synthetic answer or metric must never be presented as a real fund
fact or historical performance.

## Research Scope

- The demo contains three synthetic funds and four synthetic report periods. It
  is a software demonstration, not a cross-market fund study.
- NAV calculations use the common actual observation dates in the synthetic
  fixture. The code does not fill weekends, holidays, or missing observations.
- C10, HHI10, NameJaccard, and CommonNAVShare use public top-10 holdings only;
  they cannot establish complete portfolio exposure or overlap.
- Industry allocation is limited to fields present in the source table. Missing
  disclosure fields are not silently filled with zero.

## Retrieval and Agent Findings

- Character 2-4 gram TF-IDF measures lexical similarity; it is not semantic
  reasoning and is not a complete LLM RAG system.
- The frozen `0.31` evidence threshold is corpus-specific. It can refuse a
  question that a human could answer from a document, because conservative
  refusal is preferred to unsupported expansion.
- The 32-case, seven-suite offline evaluation is small and deterministic. Its
  32/32 result validates the listed software contracts only; it is not a
  generalization or language-quality score.
- No real LLM evaluation has been run in this public release. The optional
  online adapter is disabled and requires a separate authorization boundary.

## Product Boundary

The service does not provide real-time risk, complete holdings, trading signals,
backtests, return forecasts, or investment advice. Official-source retrieval in
the public demo is a local manifest lookup over `.invalid` URLs, not live web
scraping. Compatibility records in this directory may describe private or
excluded work; public claims are defined by the current README,
`reports/architecture.md`, and `reports/evaluation.md`.
