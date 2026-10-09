<p align="center">
  <img src="docs/images/logo.svg" width="64" height="64" alt="ChangeGuard">
</p>

<h1 align="center">ChangeGuard</h1>

<p align="center">
  <strong>Evidence-grounded risk analysis for code changes.</strong><br>
  Every finding shows how it was established. Nothing you submit is ever executed.
</p>

<p align="center">
  <a href="https://changeguard-navy.vercel.app"><strong>Open the app</strong></a> ·
  <a href="https://changeguard-navy.vercel.app/experience">Guided walkthrough</a> ·
  <a href="https://changeguard-navy.vercel.app/reports/sample">Sample report</a> ·
  <a href="https://changeguard-navy.vercel.app/evaluation">Evaluation</a> ·
  <a href="https://changeguard-navy.vercel.app/method">System card</a>
</p>

<p align="center">
  <a href="https://github.com/ChethanKMurthy/changeguard/actions/workflows/ci.yml"><img src="https://github.com/ChethanKMurthy/changeguard/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://changeguard-navy.vercel.app"><img src="https://img.shields.io/badge/app-live-1f8a4c" alt="Live"></a>
  <img src="https://img.shields.io/badge/python-3.12-3a3a3a" alt="Python 3.12">
  <img src="https://img.shields.io/badge/next.js-16-3a3a3a" alt="Next.js 16">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-3a3a3a" alt="MIT license"></a>
</p>

![ChangeGuard: a replay of a real analysis, from diff to findings](docs/images/landing.png)

## Overview

Code review catches what reviewers notice. The failures that reach production
are usually mechanical and easy to miss in a diff: a caller still passing a
keyword argument a function no longer accepts, a threshold moved by one, an
error silently swallowed, changed lines no test has ever executed.

ChangeGuard reads a change the way a careful reviewer would. It rebuilds both
revisions, follows every caller, lints only what the change introduced, and
measures test coverage of the changed lines. Each finding carries its evidence,
including the exact lines, call sites, diagnostics and coverage hits, and is
labelled by how it was established. An optional language model can explain the
results, but only claims that check out against the evidence are shown.

## What it finds

| Area | Examples | Established by |
|------|----------|----------------|
| Breaking changes | Callers that no longer bind to a changed signature, removed symbols still imported, functions that became async without their callers awaiting them | ◆ tree-sitter parsing and Python-style argument binding across files |
| Correctness and security | New lint errors only (undefined names, bare `except`), unsafe deserialisation, TLS verification disabled, SQL built from strings, shell commands from input | ◆ differential Ruff and AST pattern rules |
| Secrets and supply chain | Hard-coded credentials (masked in every output), committed `.env` files, major dependency upgrades, loosened version constraints | ◆ / ◇ secret detectors and manifest diffs |
| Data | Destructive migrations, dropped columns still referenced in code | ◆ / ◇ migration rules |
| Test risk | Changed code with no related test, changed lines the coverage report says never ran, deleted tests or assertions | ◆ / ◇ test mapping and coverage of changed lines |
| Logic and behaviour | Flipped comparisons, changed boundary constants and defaults | ◇ heuristic rules, with stated confidence |
| Prompt injection | Text in the change written to steer an AI reviewer | ◆ detection; withheld from the model |
| Model-proposed | Explanations and additional risks, only when every cited fact verifies | ✦ optional AI, capped at medium confidence |

91 rules, each with a written rationale: 40 ChangeGuard rules and 51 curated
Ruff rules run differentially. Python, JavaScript and TypeScript get full
structural analysis; secrets, migrations and dependency rules apply to any file.

## How it works

![System overview: untrusted inputs, the eleven-stage engine, the optional model zone, and the surfaces](docs/images/method-architecture.png)

- **Eleven observable stages.** Each reports its status, timing and a structured
  summary, streamed to the browser as it runs.
- **Three provenance lanes, never blended.** ◆ deterministic (established by
  analysis), ◇ heuristic (a rule's inference), ✦ AI-generated (proposed by a
  model and verified). Severity and confidence are separate categorical fields,
  never a made-up probability.
- **A transparent review priority.** Block, High, Elevated or Routine, set by a
  written rule over the findings; model findings alone can raise it to Elevated
  at most.
- **Reproducible output.** Finding IDs derive from rule and location, so the
  same change produces the same IDs on every run. The guided walkthrough checks
  this live against a recorded run.

## Results

Measured on 67 labelled code changes (65 labels, 9 safe changes as negative
controls) against two naive baselines and an ablation. Ranges in parentheses
are 95% bootstrap intervals.

| System | Precision | Recall | False alarms on safe changes |
|--------|-----------|--------|------------------------------|
| ChangeGuard, first run on holdout set 1 (21 cases, written after the rules froze) | 83.3% | 75.0% | 2 of 3 |
| ChangeGuard, first run on holdout set 2 (13 cases) | 100.0% | 81.8% | 0 of 2 |
| ChangeGuard, all cases, current rules | 100.0%&nbsp;(100–100) | 93.8%&nbsp;(88–99) | 0 of 9 |
| Same rules without the repository snapshot | 100.0%&nbsp;(100–100) | 72.3%&nbsp;(61–83) | 0 of 9 |
| Keyword-search baseline | 59.3%&nbsp;(46–73) | 49.2%&nbsp;(37–61) | 4 of 9 |
| Flag-every-change baseline | 31.4%&nbsp;(16–50) | 16.9%&nbsp;(8–27) | 9 of 9 |

No finding in any system cited evidence that failed an independent re-check.
The dataset is small and synthetic, and the same author wrote the cases and the
rules, so the clean holdout first runs are the honest estimate. The full
method, including the four labels it misses and why, is on the
[Evaluation page](https://changeguard-navy.vercel.app/evaluation) and in
[docs/EVALUATION.md](docs/EVALUATION.md).

## AI, held to the evidence

The model never sees raw input. It receives a fenced evidence pack with secrets
masked and injection-like lines withheld, and must answer in a closed JSON
schema with no file or line fields. A verifier then rejects, rather than
repairs, any claim that cites unknown evidence, names a path outside the change,
gives a line outside the cited evidence, attributes a function the evidence does
not contain, invents a number, or reports a test result.

Across three local models on the labelled set, grounding held for all of them.
Correctness did not: a 7B code model proposed 57 extra risks, all citing real
evidence, and 2 matched a label. That is why model findings live in their own
labelled lane, capped at medium confidence and never able to fail a build.

## Security and privacy

- **No execution.** Archives are read in memory with traversal, symlink and
  decompression-bomb defences. Linters read source through stdin with
  repository configuration ignored. Model output never triggers an action.
- **Secrets stay masked** in reports, exports, logs and anything sent to a model.
- **Private by default.** Each browser gets its own workspace, enforced by the
  engine; visitors cannot see each other's analyses.
- **Hardened edges.** The engine key lives only in the web app's server-side
  proxy, with rate limiting per client, size limits on every input, a
  same-origin Content Security Policy, and RFC 9457 error responses that never
  leak internals.

Threat model and mitigations: [docs/SECURITY.md](docs/SECURITY.md).

## Product tour

| | |
|---|---|
| ![Guided walkthrough: the run console after a live run](docs/images/experience-run.png) | ![Callers replayed against the new signature](docs/images/experience-callers.png) |
| **Guided walkthrough.** One change followed through every stage, run live on the engine and checked against a recording. | **Cross-file checks.** Every caller of a changed signature, bound against the new parameter list. |
| ![A report with a finding and its evidence open](docs/images/report.png) | ![Model comparison with confidence intervals](docs/images/evaluation.png) |
| **Reports.** Findings by severity and provenance, evidence with exact lines, the annotated diff, the pipeline and AI traces, and exports to Markdown, SARIF 2.1.0 and JSON. | **Evaluation.** Research-style results with intervals, clean holdout runs, misses, and a model comparison. |
| ![One recorded AI pass, from evidence pack to verified note](docs/images/experience-ai.png) | ![The app in dark mode](docs/images/landing-dark.png) |
| **Verified AI.** What the model saw, what it was allowed to say, and which claims survived verification. | **Light and dark.** Follows the system theme, with a manual switch. |

## Architecture

```
Browser ──HTTPS──▶ Web app (Next.js 16, Vercel) ──server-side proxy, API key──▶ Engine (FastAPI, Render)
                    static walkthrough, reports,                                 11-stage pipeline, SQLite,
                    evaluation and system card                                   server-sent progress events
```

| Layer | Technology |
|-------|------------|
| Analysis engine | Python 3.12, FastAPI, Pydantic, tree-sitter, Ruff, SQLite (WAL, versioned migrations) |
| Web app | Next.js 16 (App Router, Cache Components), React 19, TypeScript, Tailwind CSS 4, Motion, Shiki |
| AI (optional) | Provider adapters for local Ollama models, OpenAI-compatible servers and the Claude API; structured outputs, response cache, record and replay |
| Quality | pytest, mypy (strict), Ruff, Vitest, Testing Library, Playwright, GitHub Actions |
| Hosting | Vercel (web app), Render (engine), container images for both |

Integration surfaces: a REST API with server-sent progress events
([docs/API.md](docs/API.md)), exports to SARIF for code scanning and Markdown for
pull requests, and a CLI that gates CI on a severity threshold. The full design,
module map and AI boundary are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Engineering standards

| Gate | Coverage |
|------|----------|
| Engine tests | 182 unit and API integration tests, including input safety, workspace isolation and generated-data freshness |
| Web tests | 36 unit and component tests |
| End-to-end | 9 Playwright journeys against a production build and a real engine, desktop and mobile |
| Static checks | Ruff, mypy strict, ESLint, TypeScript |
| Evaluation gate | Every change replays the labelled evaluation, models included, and fails on any regression against a committed baseline |
| Contract | The engine's OpenAPI document generates the web app's types; drift fails the build |
| Images | Both container images build on every change |

All of it runs in [CI](.github/workflows/ci.yml) on every push.

## Documentation

| | |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | Pipeline, modules, AI boundary, storage |
| [API](docs/API.md) | Endpoints, authentication, workspaces, progress events, errors |
| [Evaluation](docs/EVALUATION.md) · [Datasheet](eval/DATASHEET.md) · [Labelling guide](eval/LABELING.md) | Method, results, and how the data was made |
| [System card](docs/SYSTEM_CARD.md) | Intended use, model constraints, known failure modes |
| [Security](docs/SECURITY.md) | Threat model, headers, hardening checklist |
| [Limitations](docs/LIMITATIONS.md) | What it cannot do |
| [Case study](docs/CASE_STUDY.md) · [Design review](docs/REVIEW.md) | Design decisions and a critical review of them |
| [Operations](docs/DEPLOYMENT.md) · [Development](docs/SETUP.md) | Hosting, configuration, and working on the code |

## Status

ChangeGuard is live at
[changeguard-navy.vercel.app](https://changeguard-navy.vercel.app). The analysis
engine runs on a free tier that sleeps when idle, so the first analysis after a
quiet period takes about a minute while it wakes. The walkthrough, sample
report, evaluation and system card are static and always load instantly. Known
limits are listed in [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## License

[MIT](LICENSE)
