# Limitations

What ChangeGuard cannot do, stated plainly. Reports repeat the ones that applied
to the run in their own `limitations` field.

## Analysis

- **Meaning, not shape.** Rules find structural and pattern-level problems. A
  reversed subtraction, a dropped factor, a timezone silently lost, or a weakened
  security constant look like correct code; the rules miss them (see the four
  misses in [EVALUATION.md](EVALUATION.md#3-what-it-misses)).
- **Static, name-based resolution.** Callers are found through imports and
  names. Dynamic dispatch, reflection, monkey-patching, dependency injection, and
  string-built imports are not followed.
- **Binding is not correctness.** A call that still binds against a new
  signature is reported as compatible even when the value it passes is now wrong
  (the guided experience shows one).
- **Structural support** covers Python, JavaScript, TypeScript and TSX. Other
  languages get line-level rules (secrets, injection text, migrations,
  dependency manifests).
- **Test mapping is static.** A test counts as related when it imports the
  symbol's module and references the symbol. Tests that exercise code indirectly
  (an API test reaching a handler) are not credited.
- **Coverage is only as fresh as the report.** A plausibility check flags reports
  that look stale and lowers confidence, but cannot prove a report current.
- **Diff-only mode** (no snapshot) cannot check callers, imports, or tests, and
  finds about a quarter fewer labelled issues on the evaluation set.
- **Severity and confidence are categorical rule judgements**, not calibrated
  probabilities. Review priority is a rule, not a risk score.

## AI synthesis

- Optional and off by default. When on, a model can explain findings and propose
  risks; it can be wrong while citing real evidence.
- The verifier checks references (evidence, paths, lines, symbols, numbers, test
  claims). It cannot check reasoning. Explanation quality has not been rated by
  people.
- Free-text summaries are kept in the JSON trace and not displayed.
- Large changes are trimmed to the context budget; the model may not see every
  finding.
- Hosted models change over time. Recorded responses make the evaluation
  reproducible, not live behaviour.

## Evaluation

- 67 synthetic cases written by the rules' author; dev-split numbers are
  optimistic by construction. See [`eval/DATASHEET.md`](../eval/DATASHEET.md).
- One labeller; label noise is unmeasured.
- Bootstrap intervals are wide at this size.

## Deployment

- One engine process: rate limiting and the job queue are in-process.
- SQLite: fine for a team-sized instance, not for many concurrent writers.
- Workspaces separate browsers; they are not user accounts.
- On free hosting tiers, reports do not persist across restarts and the engine
  sleeps when idle.
