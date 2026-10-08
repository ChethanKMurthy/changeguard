# ChangeGuard engine

The Python half of ChangeGuard: patch ingestion, the eleven-stage analysis
pipeline, optional verified AI synthesis, the HTTP API with server-sent progress,
the CLI, and the evaluation harness.

```bash
uv sync
uv run uvicorn changeguard.api.app:create_default_app --factory --reload --port 8000
uv run changeguard analyze change.patch --repo-archive base.zip --coverage coverage.xml
uv run pytest -q
uv run changeguard eval --help
```

- Source: `src/changeguard/` (module map in [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md))
- API: [../docs/API.md](../docs/API.md), or `/api/docs` on a running engine
- Configuration: `CHANGEGUARD_*` variables, listed in [../docs/SETUP.md](../docs/SETUP.md#configuration)
- Tools: `tools/export_frontend_data.py` (static data for the web app),
  `tools/make_patch.py` (git-generated patches for samples and cases)

Python 3.12, managed with uv. Lint with `uv run ruff check src tests tools`,
type-check with `uv run mypy src` (strict).
