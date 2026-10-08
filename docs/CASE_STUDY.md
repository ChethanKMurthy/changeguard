# Case study: building a code-review assistant that can show its work

## The problem

Review tools tend to fail in one of two ways. Linters run over a whole
repository and bury a reviewer in findings that predate the change. Language
model reviewers write fluent comments that are sometimes right, sometimes
invented, and always equally confident. Neither tells a reviewer how a claim was
established, so neither can be trusted with the boring, mechanical failures that
cause real outages: a caller that no longer matches a signature, a deleted test,
a threshold moved by one, a changed line no test has ever run.

ChangeGuard's premise is that every finding should carry its evidence and its
provenance, and that a weaker source of knowledge must never overrule a stronger
one.

## What it does, on one change

The bundled sample is a 29-line refactor of a billing service: loyalty
discounts are added and price formatting moves from currency codes to locales.
The engine's run, the same one the guided experience walks through:

- **Rebuilds both revisions** from the patch and a 6-file snapshot, in memory.
- **Diffs structure, not lines.** Five symbols changed; `format_price` dropped
  `currency` and gained a required `locale`, which the structural diff marks
  breaking.
- **Follows every caller.** Six call sites are bound against the new parameter
  lists using Python's argument rules. Two fail: `render_line` passes
  `currency=`, and a test omits `locale`. That is one deterministic, high-severity
  finding with both call sites as evidence.
- **Lints only what is new.** Five new Ruff diagnostics become four findings, a
  bare `except` reported by two rules being merged. Read together, two of them
  describe one bug: an undefined `REGIONAL_RATES` raises `NameError`, which the
  bare `except` swallows, so non-EU invoices silently lose regional tax.
- **Measures tests.** Two of five changed symbols have tests that import them;
  4 of 19 changed executable lines ran under the uploaded coverage report.
- **Is honest about its limits.** A third call,
  `format_price(Decimal("5"), "EUR")`, binds (the string lands in `locale`) and is
  reported as compatible, though it is wrong. Binding checks catch arity and
  keywords, not meaning; the walkthrough says so.

## Keeping the model in its lane

The model is optional and sees only a fenced, redacted evidence pack. It answers
in a closed schema without location fields, and every claim is verified against
the evidence before it is shown. On the sample, a local 3B model made two claims;
both passed, and one became a note on the call-site finding. It also wrote a
free-text summary that put the condition change in `format_price`; it is in
`apply_discount`. Free text cannot be checked claim by claim, so ChangeGuard
keeps it in the trace and never displays it as analysis.

## Measuring it without fooling myself

The evaluation was designed around one uncomfortable fact: the same person wrote
the rules and the test cases. The mitigations:

1. **Splits written in order.** Rules were developed on a dev split. Two holdout
   splits were written afterwards with the ruleset frozen, labelled before
   anything ran, and evaluated once. The first runs' raw output is committed.
2. **First-run numbers stay published** next to later ones, with every fix they
   prompted listed. The first holdout scored 83% precision and 75% recall, well
   below the dev split's 100%, and exposed real bugs: JavaScript methods treated
   as having an implicit `self`, a return annotation flagged as a type change,
   noisy test-gap findings on renames, and two unsafe-deserialisation functions
   Ruff does not cover. The second holdout found one more gap (`verify=False`
   through a session object).
3. **An ablation and naive baselines.** Removing the repository snapshot drops
   recall from 93.8% to 72.3% at the same precision, which quantifies what
   cross-file analysis contributes. A keyword search and a flag-every-change
   baseline set the floor.
4. **Evidence is re-checked independently.** For every finding, the harness
   re-reads the case files and confirms the cited lines exist and match. The
   count must be zero; CI fails otherwise.
5. **Intervals, not just points.** Bootstrap intervals over cases make the small
   sample's uncertainty visible.

## What the model results showed

Three local models, same prompt, responses recorded so CI replays them:

- A 3B model rarely proposes risks; it mostly explains findings the rules made.
- A 7B code model proposes many: 57 extra risks, all grounded in real evidence,
  of which 2 matched a label. Those 2 are exactly the semantic bugs no rule
  catches, which is the strongest argument for a model; the other 55 are false
  alarms, including one on every safe change.
- Three-sample voting removed 21 of the 57 and kept both correct ones, at three
  times the tokens.

Grounding held across all of them. Correctness did not. That result is what
fixed the product decision: model findings live in their own labelled lane,
capped at medium confidence, able to raise review priority to Elevated at most,
and never able to fail a build.

## Engineering choices worth noting

- **Safety by construction.** Archives are read in memory with traversal, link,
  bomb and size defences; Ruff reads stdin in isolated mode; git runs with hooks
  and external drivers disabled; nothing from the analysed repository executes.
- **Stable finding IDs.** IDs derive from rule and location, so a live run can be
  compared with a recording. The guided experience does exactly that.
- **Reproducible model evaluation.** Requests are fingerprinted over prompt,
  evidence and decoding settings; recordings replay exactly and a miss is an
  error, not a silent live call.
- **A contract between halves.** The engine's OpenAPI document generates the web
  app's types; CI fails on drift.
- **Privacy on shared deployments.** Each browser gets a workspace, enforced by
  the engine, so a public demo does not show one visitor another's diffs.

## What I would do next

1. **A real-world dataset.** Mine fix commits from open-source projects, label the
   introducing changes with a second annotator, and measure agreement.
2. **Human rating of model explanations**, the largest unmeasured quantity.
3. **Semantic checks with evidence.** Property-based test suggestions around
   changed comparisons and arithmetic, the category where every system here is
   weakest.
4. **More languages** with structural support (Go and Java first).
5. **Multi-instance deployment**: a shared rate limiter and Postgres.
