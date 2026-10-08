# Skeptical review

A review of this implementation as a senior engineer would review a portfolio
project: what is weak, what was fixed during the review, and what a careful
interviewer is likely to press on. Fixed items say how they were verified.

## Fixed during the final review

| # | Issue | Impact | Fix | Verified by |
|---|-------|--------|-----|-------------|
| 1 | On a shared deployment every visitor could list and open every other visitor's uploaded diffs | Privacy failure on any public demo | Per-browser workspaces: an HttpOnly cookie set by the web app, forwarded by its proxy, enforced by the engine on create, list, read, stream, export and delete; clients cannot choose the header | API tests for isolation; e2e test with two browser contexts; manual check through the proxy |
| 2 | Behind the web app every request carried the same API key, so all visitors shared one rate-limit bucket | One visitor could exhaust everyone's quota | With trusted proxy headers, the forwarded client address is the rate-limit identity | API test with two forwarded addresses |
| 3 | `force-include` in `pyproject.toml` added prompt and sample files twice, so non-editable installs failed | The engine's container image could not have built | Removed; the wheel already ships those files | Wheel inspected; engine installed non-editable outside the source tree and served the sample |
| 4 | Implicit-column CSS grids sized to their widest code line, and visually hidden text escaped scroll containers | Pages scrolled sideways on phones (233 px on the landing page) | Explicit `minmax(0, …)` columns; scroll containers made positioning contexts | e2e check at phone width on every page; overflow scan at 360 and 412 px |
| 5 | The data hook read its cache during the first render | Hydration mismatch on the guided experience | Rewritten on `useSyncExternalStore` with a server snapshot; shared requests | Unit tests; no console errors in e2e |
| 6 | The recorded report rendered a relative time during prerender | The production build failed | `RelativeTime` renders the absolute date on the server and relative time in the browser | `next build` |
| 7 | The landing page quoted only the better of the two clean holdout runs | Cherry-picked headline | Both first runs shown side by side | Page review |
| 8 | A rule-family readout labelled "error handling removed" as "swallowed errors", next to a chapter about a swallowed error | Contradictory, wrong claim | Labels now describe what each counter measures; AST pattern rules added | Tests on the derived data |
| 9 | Hosted model providers were described as supported without saying they were never run live | Unverified integration claim | Docs and the Method page say they are tested against mocked clients only | Text review |
| 10 | The Anthropic default model differed between the settings and the provider factory | Confusing configuration | Aligned on `claude-opus-5-5` | Code review |
| 11 | The OpenAPI document predated the workspace header | CI contract check would fail | Regenerated document and TypeScript types | `make contract`; CI check |
| 12 | Nothing caught the web app's generated data going stale after a rule change | Pages could show numbers the engine no longer produces | Tests compare the shipped rules, sample report and evaluation ruleset with a fresh run | New engine tests |

## Remaining weaknesses, highest impact first

1. **The evaluation is self-authored.** One person wrote the rules, the cases,
   and the labels. Holdouts, first-run records, an ablation and baselines limit
   the damage but cannot remove it. The honest headline is the first holdout run
   (83% precision, 75% recall), not the 100% / 94% overall figure. A second
   annotator and real-world cases are the most valuable next step.
2. **Semantic regressions are the blind spot.** All four misses are changes whose
   problem is meaning, not shape. Only a model found any of them, at a high
   false-alarm cost.
3. **Model explanations are unrated.** Grounding is measured; correctness and
   usefulness of explanations are not.
4. **Single-instance design.** The job queue and rate limiter are in-process and
   storage is SQLite. Fine for one team; scaling out needs a shared queue, a
   shared limiter and Postgres.
5. **Workspaces are not accounts.** They stop casual cross-visitor access, not a
   determined holder of someone's cookie. There is no sharing model.
6. **Server-sent events poll the database** every 250 ms per open stream, with no
   cap on concurrent streams.
7. **CSP allows inline scripts** (`'unsafe-inline'`), the price of static
   rendering without per-request nonces.
8. **Container images were not built on the development machine.** Their steps
   were reproduced outside Docker and CI builds them, but nothing here has run
   inside the images.

## Unnecessary complexity, considered

- **Three model providers plus replay and a cache.** Only Ollama is exercised
  end to end. The others are small adapters behind one protocol and are kept for
  users with other setups; replay is what makes model evaluation reproducible in
  CI, so it earns its place.
- **The guided experience.** It is the largest part of the web app. It earns its
  place by reusing the engine's real output and by checking reproducibility live,
  but it is presentation, not analysis.
- **91 rules.** 51 are curated Ruff rules run differentially; the catalogue says
  which. The project's own contribution is the 40 rules and the cross-file
  binding checker, and the review should credit only those.

## Questions an interviewer is likely to ask

- *Why is precision 100% on the full set?* Because the dev split was written
  alongside the rules. Point to the first holdout runs and what they exposed.
- *What does "verified" mean for AI output?* Grounded: every cited evidence ID,
  path, line, function and number checks out. It does not mean correct; the 7B
  model's grounded-but-wrong risks show the difference.
- *Why tree-sitter instead of a language server?* No project setup, no execution
  of build tooling on untrusted code, fast and uniform across languages; the cost
  is name-based rather than type-based resolution.
- *How do the bootstrap intervals work, and why over cases?* Labels within a case
  are correlated, so cases are the resampling unit.
- *What happens to a replayed evaluation if the prompt changes?* The request
  fingerprint changes, every lookup misses, and replay fails loudly rather than
  calling a model.
- *How would this scale to a monorepo?* Archive limits and the in-memory
  workspace bound it today; the path is incremental indexing and a persistent
  symbol index.
