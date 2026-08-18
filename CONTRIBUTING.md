# Contributing

Keep contributions within the public synthetic/demo boundary. Do not add
complete fund PDFs, private caches, provider responses, credentials, local
paths, or unsupported claims about real LLM performance.

Run the deterministic public checks before opening a pull request:

```powershell
python scripts/run_pipeline.py --profile demo_synthetic
python -m pytest -q
```

Docker changes must preserve the read-only synthetic-data mount, non-root user,
and disabled online mode unless a separate security review is provided.

AI-assisted development tools were used for implementation support and
documentation review. The research questions, data boundaries, methodology,
verification procedures, and final claims were selected and validated by the
author.
