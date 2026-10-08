# Evaluation

Results below are from ruleset `2026.10.4` on the dataset at SHA-256
`b65381532aba57ce…` (67 cases, 65 labels, 9 negative controls). The complete,
regenerated report is [`eval/reports/latest.md`](../eval/reports/latest.md); the web
app's Evaluation page renders the same data with intervals. How the dataset was
built, and what it is not, is in [`eval/DATASHEET.md`](../eval/DATASHEET.md).

**Read this first.** The dataset is small and synthetic, and the same person
wrote it and the rules. The numbers measure agreement with the labelling guide
on these cases. They are not estimates of effectiveness on real repositories,
and nothing here estimates the probability of an incident.

## 1. Clean holdout results (the least biased numbers)

Each holdout split was written after the ruleset was frozen, labelled before any
system ran, and evaluated once. These are those first runs, before any fix they
prompted.

| Split | Ruleset | System | Precision | Recall | F1 | False alarms on safe changes |
|-------|---------|--------|-----------|--------|----|------------------------------|
| holdout (21 cases) | 2026.10.1 | ChangeGuard | 83.3% | 75.0% | 79.0% | 2 of 3 |
| | | ChangeGuard, diff only | 90.9% | 50.0% | 64.5% | 1 of 3 |
| | | Keyword baseline | 57.1% | 40.0% | 47.1% | 2 of 3 |
| | | Flag-every-change baseline | 27.3% | 15.0% | 19.4% | 3 of 3 |
| holdout-v2 (13 cases) | 2026.10.2 | ChangeGuard | 100.0% | 81.8% | 90.0% | 0 of 2 |
| | | ChangeGuard, diff only | 100.0% | 63.6% | 77.8% | 0 of 2 |
| | | Keyword baseline | 42.9% | 27.3% | 33.3% | 1 of 2 |
| | | Flag-every-change baseline | 42.9% | 27.3% | 33.3% | 2 of 2 |

What changed after each first run (so later numbers on these splits are
optimistic):

- **holdout:** JavaScript/TypeScript methods were wrongly given an implicit
  `self` parameter, hiding new required parameters (fixed). Adding a return
  annotation where none existed was reported as a return-type change (fixed).
  Pure renames and private helpers with tested same-file callers no longer
  produce test-gap findings. `yaml.unsafe_load`, `marshal.loads` and
  `jsonpickle.decode` detection was added. One label correction: an omitted
  acceptable test-gap entry in `ho-py-dataclass-001`, under `LABELING.md` §4.
- **holdout-v2:** `verify=False` passed through `Session`/`Client` methods is
  now detected (Ruff's S501 only matches module-level `requests` calls).

## 2. All cases, current ruleset

95% percentile bootstrap intervals over cases, 2,000 resamples.

| System | Precision | Recall | F1 | False alarms on safe changes | Unsupported evidence |
|--------|-----------|--------|----|------------------------------|----------------------|
| ChangeGuard (rules) | 100.0% [100–100] | 93.8% [88–99] | 96.8% | 0/9 | 0/102 |
| + llama3.2:3b | 98.4% [95–100] | 93.8% [88–99] | 96.1% | 0/9 | 0/103 |
| + qwen2.5-coder:7b | 53.4% [49–58] | 96.9% [92–100] | 68.8% | 9/9 | 0/159 |
| + qwen2.5-coder:7b, 3-sample vote | 65.0% [59–71] | 96.9% [92–100] | 77.8% | 7/9 | 0/138 |
| ChangeGuard, diff only (ablation) | 100.0% [100–100] | 72.3% [61–83] | 83.9% | 0/9 | 0/48 |
| Keyword baseline | 59.3% [46–73] | 49.2% [37–61] | 53.8% | 4/9 | — |
| Flag-every-change baseline | 31.4% [16–50] | 16.9% [8–27] | 22.0% | 9/9 | — |

These include the dev split the rules were written against and the holdout
cases after their fixes. By split, ChangeGuard's recall is 100% (dev), 85.0%
(holdout) and 90.9% (holdout-v2), with precision 100% on all three.

The ablation is the clearest result: without the repository snapshot the same
rules keep their precision, but recall falls from 93.8% to 72.3%. That gap is
what reconstructing both revisions and following callers, imports and tests
contributes.

## 3. What it misses

Four labels are missed, all changes whose problem is in their meaning rather
than their shape:

| Case | What is wrong | Found by |
|------|---------------|----------|
| `ho-py-semantic-001` | Operands of a refund subtraction swapped | qwen2.5-coder:7b (both variants) |
| `ho-py-semantic-002` | Quantity dropped from a total during a refactor | qwen2.5-coder:7b (both variants), keyword baseline |
| `h2-py-naive-datetime-001` | UTC timestamps become naive local time | none |
| `ho-py-test-deleted-001` (L2) | PBKDF2 iteration count halved | none |

## 4. Language models

All three ran locally through Ollama with the same prompt (`review` v1.0.0),
temperature 0 and seed 7; the vote variant samples three answers at temperature
0.7 and keeps a proposed risk only when a majority agree. Every response is
recorded, so CI replays these numbers without a model.

| Model | Claims (rejected) | Notes attached | Model-proposed risks (matched a label) | Mean latency | Tokens in/out |
|-------|-------------------|----------------|----------------------------------------|--------------|---------------|
| llama3.2:3b | 190 (20) | 97 | 1 (0) | 4.9 s | 986/340 |
| qwen2.5-coder:7b | 241 (3) | 101 | 57 (2) | 13.6 s | 1016/436 |
| qwen2.5-coder:7b, 3-sample vote | 241 (26) | 101 | 36 (2) | 40.2 s | 3049/1305 |

Rejection reasons: llama3.2:3b mostly cited findings that did not exist
(`unknown_finding` ×14) or named functions absent from its evidence
(`symbol_not_in_evidence` ×5); the vote variant's rejections are mostly
`low_agreement` (×23).

Findings:

1. **Grounding held.** No system produced a finding with unsupported evidence,
   and the verifier rejected the claims that would have introduced some.
2. **Grounded is not correct.** qwen2.5-coder:7b proposed 57 extra risks that all
   cite real evidence; 2 matched a label. Those 2 are the semantic bugs no rule
   catches, which is the case for a model, but they arrive with 55 false alarms
   and a false alarm on every safe change.
3. **Voting helps at a price.** Three-sample voting dropped 21 of the 57 proposals,
   kept both correct ones, and cut false alarms on safe changes from 9/9 to 7/9,
   at about three times the tokens.
4. **Not measured:** whether explanations are correct or useful. That needs human
   rating, which has not been done.

This is why model findings are a separate lane: labelled, confidence capped at
medium, able to raise review priority at most to Elevated, and never counted by
`--fail-on`.

## 5. Method

- **Matching:** same category and file, line ranges overlapping within ±3 lines,
  one-to-one. Predictions matching an acceptable observation, or duplicating a
  matched label, count as neither true nor false positives.
- **Metrics:** micro-averaged precision, recall and F1; share of negative controls
  with any finding; findings whose evidence fails an independent re-check against
  the case files; precision by provenance and confidence; severity agreement
  (93.4% exact, 100% within one level for ChangeGuard).
- **Intervals:** percentile bootstrap over cases, 2,000 resamples, seed 20261008.
- **Regression gate:** CI replays the evaluation and fails if precision, recall or
  F1 drops by more than 2 points, the false-alarm rate rises by more than 5,
  unsupported evidence increases, or a previously found label is missed
  (`eval/baselines/changeguard.json`).
- **Reproduce:** `make eval-check`, or see [`eval/README.md`](../eval/README.md).
