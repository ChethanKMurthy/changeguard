# HTTP API

Base path `/api/v1`. The engine serves interactive documentation at `/api/docs`
(Swagger UI), `/api/redoc`, and the OpenAPI document at `/api/openapi.json`
unless `CHANGEGUARD_EXPOSE_DOCS=false`. The web app proxies the same API on its
own origin, so every example below also works against `http://localhost:3000`.

## Authentication

When `CHANGEGUARD_API_KEYS` is set (comma-separated), every endpoint except
`/health`, `/meta`, `/rules`, `/samples` (read-only) and `/evaluation` requires a
key, sent as either header:

```
Authorization: Bearer <key>
X-API-Key: <key>
```

Keys are compared in constant time. Without configured keys the API is open,
which is only appropriate on a private network or localhost.

## Workspaces

`X-ChangeGuard-Workspace: <16–64 of A–Z a–z 0–9 - _>` scopes a request. With the
header, an analysis is created in that workspace, and listing, reading,
streaming, exporting and deleting only see analyses from it; anything else
returns `404` as if it did not exist. Without the header the request is
unscoped (operator access). The web app sets the header from an HttpOnly cookie
and ignores any value a browser sends.

## Rate limits

`POST` endpoints that start analyses are limited per client
(`CHANGEGUARD_RATE_LIMIT_PER_MINUTE`, default 20, sliding window). The client is
the first `X-Forwarded-For` address when `CHANGEGUARD_TRUST_PROXY_HEADERS=true`,
otherwise the API key, otherwise the socket address. Exceeding it returns `429`
with `Retry-After`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness probe: `{"status":"ok","version":…}` |
| `GET` | `/meta` | Version, ruleset, limits, supported formats, stages, AI provider status |
| `GET` | `/rules` | Every rule: ID, title, category, provenance, default severity, rationale, languages |
| `GET` | `/samples` | Built-in sample scenarios (labelled synthetic) |
| `GET` | `/samples/{id}` | One sample, including its patch |
| `POST` | `/samples/{id}/analyses` | Analyse a sample. Query: `ai`, `snapshot`, `coverage` (booleans) |
| `POST` | `/analyses` | Start an analysis (multipart, below) → `202` with the analysis summary |
| `GET` | `/analyses` | List analyses, newest first. Query: `limit` (1–100), `offset`, `q` (title search) |
| `GET` | `/analyses/{id}` | Status, summary, and (when completed) the full report |
| `GET` | `/analyses/{id}/events` | Progress as server-sent events |
| `GET` | `/analyses/{id}/export?format=json\|markdown\|sarif` | Download a completed report |
| `DELETE` | `/analyses/{id}` | Delete an analysis and its events → `204` |
| `GET` | `/evaluation` | The latest bundled evaluation report, when present |

### Starting an analysis

`multipart/form-data` fields:

| Field | Type | |
|-------|------|---|
| `patch` | file | Unified diff or `git diff` output. Or send `patch_text`. |
| `patch_text` | text | The diff as text. |
| `repository` | file | Optional `.zip`, `.tar`, `.tar.gz` of the **base** revision. Enables cross-file analysis. |
| `coverage` | file | Optional Cobertura XML, LCOV, or coverage.py JSON for the **head** revision. |
| `title` | text | Optional, ≤ 200 characters. |
| `ai` | boolean | Run AI synthesis if a provider is configured. |

```bash
curl -s -X POST http://localhost:8000/api/v1/analyses \
  -F patch=@change.patch \
  -F repository=@base.zip \
  -F coverage=@coverage.xml \
  -F title="Loyalty discounts"
```

```json
{
  "id": "an_6d41a3…",
  "status": "queued",
  "links": {
    "self": "/api/v1/analyses/an_6d41a3…",
    "events": "/api/v1/analyses/an_6d41a3…/events",
    "export_markdown": "/api/v1/analyses/an_6d41a3…/export?format=markdown"
  }
}
```

### Progress events

`GET /analyses/{id}/events` returns `text/event-stream`. Every event has an `id`
(resume with `Last-Event-ID`), an `event` type, and JSON `data`:

```
event: started
data: {"type":"started","analysis_id":"an_…"}

event: stage
data: {"type":"stage","status":"running","name":"structure","label":"Structural diff"}

event: stage
data: {"type":"stage","name":"structure","label":"Structural diff","status":"ok","duration_ms":1.6,
       "summary":{"changed_symbols":5,"breaking":1},"notes":[]}

event: completed
data: {"type":"completed","analysis_id":"an_…","duration_ms":41.0,"summary":{…}}
```

A failed analysis ends with `event: failed` and `{"error":{"code":…,"message":…}}`.

### The report

`GET /analyses/{id}` returns the report (schema `1.0`) once `status` is
`completed`. Its main parts:

| Field | Contents |
|-------|----------|
| `summary` | Counts by severity, provenance, category; changed and breaking symbols; patch coverage; review priority with the finding IDs that set it |
| `findings[]` | `id`, `rule_id`, `category`, `kind` (provenance), `severity`, `confidence`, `location`, `evidence_ids`, `description`, `failure_scenario`, `suggested_test`, `explanation`, `corroborated_by`, optional `ai_analysis` |
| `evidence[]` | `id` (`E1`…), `type`, `file`, lines, `side`, verbatim `excerpt`, `source`, structured `data` |
| `files[]` | Changed files with redacted hunks and per-file coverage |
| `symbols[]` | Changed symbols with signatures before and after, call sites, tests, complexity |
| `pipeline[]` | Every stage's status, duration, summary, notes |
| `ai` | Provider, model, prompt version and hash, per-call trace, verification counts and rejections |
| `warnings`, `limitations` | What this run could not do |

The full schema is in the OpenAPI document.

## Errors

Errors use RFC 9457 problem details (`application/problem+json`) with a stable
`code`:

```json
{
  "type": "about:blank",
  "title": "Malformed patch",
  "status": 422,
  "detail": "no file changes found; expected a unified diff (git diff, git format-patch, or diff -u)",
  "code": "malformed_patch",
  "request_id": "c65b1c31cdba459f",
  "meta": {}
}
```

`request_id` matches the `X-Request-ID` response header (a client may supply its
own). Unexpected server errors are logged with it.

| Status | Codes |
|--------|-------|
| 401 | `unauthorized` |
| 404 | `not_found` |
| 413 | `payload_too_large` |
| 415 | `unsupported_input` |
| 422 | `invalid_request` (parameter validation), `invalid_input`, `malformed_patch`, `invalid_archive`, `invalid_coverage_report` |
| 429 | `rate_limited` |
| 500 | `internal_error` |

Messages never contain stack traces, server paths, or uploaded content.
