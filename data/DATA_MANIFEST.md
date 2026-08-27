# Public Data Manifest

| Path | Classification | Source | Rights reference | Included fields | Publication rationale | Limitations |
| --- | --- | --- | --- | --- | --- | --- |
| `data/demo_synthetic/profile.json` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | profile flags and row counts | Contains no real entity or performance data | Software demonstration only |
| `data/demo_synthetic/nav_daily.csv` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | synthetic code, date, NAV, reserved-domain URL | Deterministic fictitious series | Not market performance |
| `data/demo_synthetic/nav_metrics.csv` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | return, volatility, drawdown | Derived only from synthetic NAV | Not investment evidence |
| `data/demo_synthetic/top10_holdings.csv` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | fictitious holdings and weights | Uses invented securities and funds | Not a real portfolio |
| `data/demo_synthetic/holding_metrics.csv` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | C10 and HHI10 | Derived only from synthetic holdings | Public-top-10 contract demo |
| `data/demo_synthetic/public_top10_overlap.csv` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | Jaccard and common NAV share | Derived only from synthetic holdings | Not complete-portfolio overlap |
| `data/demo_synthetic/industry_allocation.csv` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | fictitious industry allocations | Contains invented categories and amounts | Not real disclosure data |
| `data/demo_synthetic/return_correlation.csv` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | pairwise synthetic return correlations | Derived only from synthetic NAV | No forecasting meaning |
| `data/demo_synthetic/chunks.jsonl` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | synthetic evidence text and citations | Text states that it is synthetic | Does not support real fund claims |
| `data/demo_synthetic/tfidf_index.json` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | deterministic character n-gram index | Built only from synthetic chunks | Lexical retrieval only |
| `data/demo_synthetic/source_manifest.csv` | `SYNTHETIC` | `scripts/prepare_demo_data.py` | Project-generated fixture | synthetic document IDs, hashes, `.invalid` URLs | Reserved domain and invented records | No downloadable source document |
| `results/v2_agent/phase6/**` | `DERIVED_AGGREGATE` | Phase 6 deterministic tools | Project-generated evaluation output | contracts, summaries, hashes, redacted audit | Reproducible from included synthetic data | Not real research performance |
| `results/v2_agent/phase7_offline/**` | `DERIVED_AGGREGATE` | Phase 7 deterministic mock evaluation | Project-generated evaluation output | case outcomes, aggregate metrics, redacted traces | Reproducible with zero model/network calls | Does not validate real LLM quality |
| Historical real-fund source files and excerpts | `PRIVATE_OR_RESTRICTED_EXCLUDED` | Original official sources | Source-owner terms apply | none | Redistribution rights were not established | Obtain from original sources |

