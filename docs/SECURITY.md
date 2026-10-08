# Security

## Threat model

ChangeGuard's inputs are attacker-controlled: a patch, an archive of a
repository, a coverage report, and the code and comments inside them. The
engine treats all of it as data. It never executes analysed code, never runs
repository scripts or hooks, and never lets model output trigger an action.

| Asset | Threat | Mitigation | Where |
|-------|--------|------------|-------|
| Engine host | Archive path traversal, symlinks, device files | Members read in memory; absolute paths, `..`, drive letters, NUL bytes rejected; links and special files ignored | `ingest/archive.py` |
| Engine host | Decompression bombs, member floods | Caps on members, per-file size, and total decompressed bytes, enforced on bytes actually read; compression-ratio limit | `ingest/archive.py` |
| Engine host | Oversized or adversarial patches | Strict parser; byte, line and file limits; absolute and parent-relative paths rejected | `ingest/diff_parser.py` |
| Engine host | XML entity attacks in coverage | `defusedxml`, size limit | `ingest/coverage.py` |
| Engine host | Code execution through analysis tooling | Ruff reads stdin with `--isolated`, `--no-cache`, a minimal environment and a timeout; no repository configuration is loaded | `analysis/static_checks.py` |
| CI host | Code execution through git | `--git-repo` mode disables hooks, external diff drivers, textconv, fsmonitor and pagers | `cli.py` |
| Secrets in changes | Leaking into reports, exports, logs, prompts | Detected and masked in evidence, hunks, titles and descriptions before anything is stored, exported or sent to a model | `analysis/secrets.py`, `analysis/context.py`, `report/builder.py` |
| Reviewers | Prompt injection in code or comments | Detection rule; flagged lines withheld from the model; excerpts fenced as untrusted data; closed output schema; claims verified | `analysis/textual.py`, `ai/context.py`, `ai/grounding.py` |
| Reviewers | Model hallucination shown as fact | No location fields in the model schema; verifier rejects unsupported claims; model findings capped and labelled; free text not displayed | `ai/` |
| Web users | Script injection from analysed content | Text rendered as React text nodes; syntax highlighting emits token spans, never HTML; same-origin CSP; `frame-ancestors 'none'` | `frontend/` |
| Web users | Reading another visitor's reports | Per-browser workspace (HttpOnly, SameSite=Lax, Secure over HTTPS) enforced by the engine; clients cannot set the workspace header through the proxy | `api/deps.py`, `frontend/src/app/api/v1` |
| Engine API | Unauthorised use | Optional API keys (constant-time comparison); the web app holds the key server-side | `api/security.py` |
| Engine API | Abuse and denial of service | Per-client sliding-window rate limit, request body limit, per-analysis timeout, bounded worker pool, stored-analysis cap | `api/` |
| Operators | Credential leakage | Settings use `SecretStr`; keys never logged or returned; problem responses carry no stack traces or server paths | `config.py`, `errors.py` |

## Response headers

- Engine: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-site`,
  `Permissions-Policy`, `Cache-Control: no-store` on analysis data, and an
  `X-Request-ID` on every response. No `Server` header in the container image.
- Web app: a same-origin Content Security Policy (`default-src 'self'`,
  `connect-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`), plus
  `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` and `Permissions-Policy`.
  `script-src` allows `'unsafe-inline'` for Next.js's inline bootstrap; removing
  it would require per-request nonces and make every page dynamic.

## Hardening checklist for a deployment

- [ ] Set `CHANGEGUARD_API_KEYS` on the engine and the same value as
      `CHANGEGUARD_API_KEY` on the web app.
- [ ] Set `CHANGEGUARD_TRUST_PROXY_HEADERS=true` only when a proxy you control
      sets `X-Forwarded-For`.
- [ ] Turn off the engine's API docs on public hosts (`CHANGEGUARD_EXPOSE_DOCS=false`).
- [ ] Decide who may use the app: deployment protection or SSO if not everyone.
- [ ] Keep hosted AI providers off unless sending redacted evidence to them is acceptable.
- [ ] Serve over HTTPS (the workspace cookie is marked `Secure` on HTTPS requests).
- [ ] Back up the SQLite volume if reports matter.

## Known limitations

- Workspaces are not accounts. A cookie can be copied, and there is no sharing
  model between workspaces.
- Rate limiting is in-process: correct for one engine instance, not for several.
- `'unsafe-inline'` in `script-src`, as above.
- Secret detection uses provider-specific formats and entropy heuristics; it can
  miss secrets and can flag high-entropy non-secrets.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through the repository's
security advisory feature rather than a public issue.
