# Setup

## Requirements

| Tool | Version | For |
|------|---------|-----|
| Python | 3.12 (3.11+ supported) | the engine |
| [uv](https://docs.astral.sh/uv/) | 0.11+ | Python dependencies and commands |
| Node.js | 24 LTS (20.9+ supported) | the web app |
| git | any recent | the CLI's `--git-repo` mode, building cases |
| Ollama | optional | free local AI synthesis |
| Docker | optional | the container setup |

## Local development

```bash
make setup     # uv sync (engine) + npm ci (web app)
make dev       # engine on :8000 with reload, web app on :3000
```

Open http://localhost:3000. Engine API docs are at http://localhost:8000/api/docs.
`make help` lists every command.

Without `make`:

```bash
cd backend && uv sync && uv run uvicorn changeguard.api.app:create_default_app --factory --reload --port 8000
cd frontend && npm ci && CHANGEGUARD_API_URL=http://127.0.0.1:8000 npm run dev
```

## With Docker

```bash
cp .env.example .env            # optional; every setting has a default
docker compose up --build
docker compose --profile ai up --build    # also runs Ollama
docker compose exec ollama ollama pull llama3.2:3b
```

Both ports bind to localhost only. Reports persist in the `engine-data` volume.

## Optional: local AI

```bash
ollama pull llama3.2:3b
CHANGEGUARD_AI_PROVIDER=ollama CHANGEGUARD_AI_MODEL=llama3.2:3b make dev
```

Enable "AI synthesis" when analysing. The model runs on your machine; nothing is
sent anywhere else. This is the only provider exercised end to end in this
repository (the evaluation's recordings come from it). The hosted providers below
are implemented and covered by tests against mocked clients, but have not been
run against the live services here. To use the Claude API, set
`CHANGEGUARD_AI_PROVIDER=anthropic` and `CHANGEGUARD_AI_API_KEY` (billed by Anthropic;
`claude-opus-5-5` by default, override with `CHANGEGUARD_AI_MODEL`). Any
OpenAI-compatible server (vLLM, LM Studio) works with `CHANGEGUARD_AI_PROVIDER=openai`
and `CHANGEGUARD_AI_BASE_URL`.

## The CLI

```bash
cd backend
uv run changeguard analyze change.patch --repo-archive base.zip --coverage coverage.xml
uv run changeguard analyze --git-repo /path/to/repo --base origin/main --head HEAD --format markdown
uv run changeguard analyze --git-repo . --base origin/main --format sarif -o changeguard.sarif --fail-on high
uv run changeguard samples
uv run changeguard serve --port 8000
uv run changeguard eval --help
```

`--fail-on` exits with code 1 when a deterministic or heuristic finding at or
above the given severity exists (AI findings never count); invalid input or a
git error exits with 2.

## Tests

```bash
make test          # engine: pytest (unit + API integration); web: Vitest + Testing Library
make e2e           # Playwright against a production build and a real engine
make lint typecheck
make eval-check    # evaluation regression gate (replayed models; no model needed)
```

## Configuration

### Engine (`CHANGEGUARD_*`)

| Variable | Default | |
|----------|---------|---|
| `DATABASE_PATH` | `data/changeguard.db` | SQLite file (created on start) |
| `API_KEYS` | none | Comma-separated keys; when set, analysis endpoints require one |
| `TRUST_PROXY_HEADERS` | `false` | Rate-limit by `X-Forwarded-For` (set behind the web app or a proxy) |
| `RATE_LIMIT_PER_MINUTE` | `20` | Analyses started per client per minute |
| `CORS_ORIGINS` | none | Only needed if browsers call the engine directly |
| `EXPOSE_DOCS` | `true` | Serve `/api/docs`, `/api/redoc`, `/api/openapi.json` |
| `MAX_PATCH_BYTES` | 2 MB | Also `MAX_PATCH_LINES` (200,000), `MAX_PATCH_FILES` (500) |
| `MAX_ARCHIVE_BYTES` | 25 MB | Also `MAX_ARCHIVE_UNCOMPRESSED_BYTES` (150 MB), `MAX_ARCHIVE_MEMBERS` (20,000), `MAX_SOURCE_FILE_BYTES` (1 MB) |
| `MAX_COVERAGE_BYTES` | 20 MB | |
| `WORKER_THREADS` | `2` | Concurrent analyses |
| `ANALYSIS_TIMEOUT_SECONDS` | `240` | Per analysis |
| `MAX_STORED_ANALYSES` | `500` | Older analyses are pruned |
| `AI_PROVIDER` | `none` | `none`, `ollama`, `openai`, `anthropic`, `replay` |
| `AI_MODEL` | per provider | `llama3.2:3b` (Ollama), `claude-opus-5-5` (Anthropic) |
| `AI_BASE_URL` | per provider | e.g. `http://localhost:11434` for Ollama |
| `AI_API_KEY` | none | For hosted providers |
| `AI_TIMEOUT_SECONDS` | `90` | Per model call |
| `AI_MAX_CONTEXT_CHARS` | `24000` | Evidence pack budget; also `AI_MAX_FINDINGS` (8) |
| `AI_TEMPERATURE`, `AI_SEED` | `0`, `7` | Where the provider supports them |
| `AI_CACHE_ENABLED` | `true` | Cache responses by request fingerprint |
| `LOG_LEVEL` | `INFO` | |

### Web app

| Variable | Default | |
|----------|---------|---|
| `CHANGEGUARD_API_URL` | `http://127.0.0.1:8000` | Where the API proxy finds the engine |
| `CHANGEGUARD_API_KEY` | none | Sent to the engine by the proxy; never exposed to browsers |
| `CHANGEGUARD_WORKSPACES` | per-browser | `shared` lets every visitor see every report |

## Regenerating generated files

| Command | Regenerates |
|---------|-------------|
| `make contract` | `frontend/openapi.json` and `frontend/src/lib/api/schema.d.ts` from the engine |
| `make data` | the recorded sample report, rule catalogue, and their exports for the web app |
| `make eval` | `eval/reports/latest.*` and the web app's evaluation data |
