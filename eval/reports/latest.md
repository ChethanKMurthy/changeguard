# ChangeGuard evaluation report

Generated 2026-10-08T16:43:36+00:00 · ChangeGuard 0.1.0 · ruleset 2026.10.4

Dataset: 67 cases (33 dev, 21 holdout, 13 holdout-v2), 65 labels, 9 negative controls · sha256 `b65381532aba57ce…`

Matching: same category and file, line ranges overlapping within ±3 lines, one-to-one. Confidence intervals: 95% percentile bootstrap over cases (2000 resamples, seed 20261008).

## Systems

| System | Precision [95% CI] | Recall [95% CI] | F1 | Neg. control FP rate | Unsupported evidence |
|---|---|---|---|---|---|
| `changeguard` — Deterministic + heuristic rules (no AI) | 100.0% [100–100] | 93.8% [88–99] | 96.8% | 0.0% (0/9) | 0/102 |
| `changeguard+ai:llama3.2:3b` — Rules + AI synthesis (ollama/llama3.2:3b, replay) | 98.4% [95–100] | 93.8% [88–99] | 96.1% | 0.0% (0/9) | 0/103 |
| `changeguard+ai:qwen2.5-coder:7b` — Rules + AI synthesis (ollama/qwen2.5-coder:7b, replay) | 53.4% [49–58] | 96.9% [92–100] | 68.8% | 100.0% (9/9) | 0/159 |
| `changeguard+ai:qwen2.5-coder:7b@3` — Rules + AI synthesis (ollama/qwen2.5-coder:7b, 3-sample self-consistency, replay) | 65.0% [59–71] | 96.9% [92–100] | 77.8% | 77.8% (7/9) | 0/138 |
| `changeguard-diff-only` — Same rules without the repository snapshot (ablation) | 100.0% [100–100] | 72.3% [61–83] | 83.9% | 0.0% (0/9) | 0/48 |
| `baseline-keyword` — Regex search for risky-looking tokens on added lines | 59.3% [46–73] | 49.2% [37–61] | 53.8% | 44.4% (4/9) | — |
| `baseline-changed-symbols` — Flag every changed function (signature changes as breaking) | 31.4% [16–50] | 16.9% [8–27] | 22.0% | 100.0% (9/9) | — |

## Clean holdout estimates (first run, before any holdout-informed change)

| Split | Ruleset | System | Precision | Recall | F1 | Neg. control FP rate |
|---|---|---|---|---|---|---|
| holdout | 2026.10.1 | `changeguard` | 83.3% | 75.0% | 79.0% | 66.7% |
| holdout | 2026.10.1 | `changeguard-diff-only` | 90.9% | 50.0% | 64.5% | 33.3% |
| holdout | 2026.10.1 | `baseline-keyword` | 57.1% | 40.0% | 47.1% | 66.7% |
| holdout | 2026.10.1 | `baseline-changed-symbols` | 27.3% | 15.0% | 19.4% | 100.0% |
| holdout-v2 | 2026.10.2 | `changeguard` | 100.0% | 81.8% | 90.0% | 0.0% |
| holdout-v2 | 2026.10.2 | `changeguard-diff-only` | 100.0% | 63.6% | 77.8% | 0.0% |
| holdout-v2 | 2026.10.2 | `baseline-keyword` | 42.9% | 27.3% | 33.3% | 50.0% |
| holdout-v2 | 2026.10.2 | `baseline-changed-symbols` | 42.9% | 27.3% | 33.3% | 100.0% |

Changes made after each first run (later numbers on that split are optimistic):

- **holdout**: Fixed: JavaScript/TypeScript methods were treated as having an implicit `self` parameter, hiding new required parameters (ho-ts-method-001). Fixed: adding a return annotation where none existed was reported as a return-type change (ho-py-neg-logging-001). Changed: pure renames and private helpers whose same-file callers are tested no longer produce test-gap findings (ho-ts-neg-rename-001). Added: yaml.unsafe_load / marshal.loads / jsonpickle.decode detection, not covered by Ruff (ho-py-unsafe-load-001). Label correction: an omitted acceptable test-gap entry was added to ho-py-dataclass-001, per LABELING.md section 4.
- **holdout-v2**: Added: verify=False passed through Session/Client methods (Ruff S501 only matches module-level requests calls) (h2-py-session-verify-001).

## `changeguard` by split

| Split | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| dev | 34 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| holdout | 17 | 0 | 3 | 100.0% | 85.0% | 91.9% |
| holdout-v2 | 10 | 0 | 1 | 100.0% | 90.9% | 95.2% |

## `changeguard` by category

| Category | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| behavior_change | 1 | 0 | 1 | 100.0% | 50.0% |
| breaking_change | 15 | 0 | 0 | 100.0% | 100.0% |
| concurrency | 3 | 0 | 0 | 100.0% | 100.0% |
| correctness | 2 | 0 | 0 | 100.0% | 100.0% |
| coverage_gap | 1 | 0 | 0 | 100.0% | 100.0% |
| data_migration | 4 | 0 | 0 | 100.0% | 100.0% |
| dependency | 5 | 0 | 0 | 100.0% | 100.0% |
| error_handling | 4 | 0 | 0 | 100.0% | 100.0% |
| logic_change | 3 | 0 | 2 | 100.0% | 60.0% |
| prompt_injection | 1 | 0 | 0 | 100.0% | 100.0% |
| secret_exposure | 2 | 0 | 0 | 100.0% | 100.0% |
| security | 15 | 0 | 1 | 100.0% | 93.8% |
| test_integrity | 5 | 0 | 0 | 100.0% | 100.0% |

## `changeguard` precision by provenance and confidence

| Group | TP | FP | Acceptable | Precision |
|---|---|---|---|---|
| kind: deterministic | 50 | 0 | 1 | 100.0% |
| kind: heuristic | 11 | 0 | 40 | 100.0% |
| confidence: high | 52 | 0 | 0 | 100.0% |
| confidence: medium | 9 | 0 | 41 | 100.0% |

Severity agreement on matched findings: exact 93.4%, within one level 100.0%.

## AI synthesis

### `changeguard+ai:llama3.2:3b`

- Model calls completed for 67/67 cases (0 failed, 0 replay misses).
- Claims: 190 made, 20 rejected by grounding verification (rejection rate 10.5%).
- Rejection reasons: unknown_finding × 14, symbol_not_in_evidence × 5, no_evidence × 1, unknown_path × 1
- Explanations attached to deterministic findings: 97; AI-only findings: 1 (0 matched a label).
- Mean model latency 4.9s; mean tokens in/out 986/340.

### `changeguard+ai:qwen2.5-coder:7b`

- Model calls completed for 67/67 cases (0 failed, 0 replay misses).
- Claims: 241 made, 3 rejected by grounding verification (rejection rate 1.2%).
- Rejection reasons: unknown_path × 2, symbol_not_in_evidence × 1
- Explanations attached to deterministic findings: 101; AI-only findings: 57 (2 matched a label).
- Mean model latency 13.6s; mean tokens in/out 1016/436.

### `changeguard+ai:qwen2.5-coder:7b@3`

- Model calls completed for 67/67 cases (0 failed, 0 replay misses).
- Claims: 241 made, 26 rejected by grounding verification (rejection rate 10.8%).
- Rejection reasons: low_agreement × 23, unknown_path × 2, symbol_not_in_evidence × 1
- Explanations attached to deterministic findings: 101; AI-only findings: 36 (2 matched a label).
- Mean model latency 40.2s; mean tokens in/out 3049/1305.

## Per-case results

| Case | Split | Matched | Missed | False positives |
|---|---|---|---|---|
| `h2-js-describe-skip-001` | holdout-v2 | L1 | — | — |
| `h2-py-flask-debug-001` | holdout-v2 | L1 | — | — |
| `h2-py-jwt-001` | holdout-v2 | L1 | — | — |
| `h2-py-kwonly-001` | holdout-v2 | L1 | — | — |
| `h2-py-naive-datetime-001` | holdout-v2 | — | L1 | — |
| `h2-py-neg-validation-001` (negative) | holdout-v2 | — | — | — |
| `h2-py-session-verify-001` | holdout-v2 | L1 | — | — |
| `h2-py-staticmethod-001` | holdout-v2 | L1 | — | — |
| `h2-py-timeout-handling-001` | holdout-v2 | L1 | — | — |
| `h2-sql-rename-column-001` | holdout-v2 | L1 | — | — |
| `h2-ts-neg-extract-001` (negative) | holdout-v2 | — | — | — |
| `h2-ts-optional-required-001` | holdout-v2 | L1 | — | — |
| `h2-tsx-innerhtml-001` | holdout-v2 | L1 | — | — |
| `ho-js-commonjs-001` | holdout | L1 | — | — |
| `ho-js-neg-reduce-001` (negative) | holdout | — | — | — |
| `ho-py-alias-module-001` | holdout | L1 | — | — |
| `ho-py-async-sleep-001` | holdout | L1 | — | — |
| `ho-py-dataclass-001` | holdout | L1 | — | — |
| `ho-py-diffonly-tls-001` | holdout | L1 | — | — |
| `ho-py-injection-001` | holdout | L1, L2 | — | — |
| `ho-py-moved-module-001` | holdout | L1 | — | — |
| `ho-py-mutable-default-001` | holdout | L1 | — | — |
| `ho-py-neg-logging-001` (negative) | holdout | — | — | — |
| `ho-py-pickle-001` | holdout | L1 | — | — |
| `ho-py-popen-shell-001` | holdout | L1 | — | — |
| `ho-py-semantic-001` | holdout | — | L1 | — |
| `ho-py-semantic-002` | holdout | — | L1 | — |
| `ho-py-test-deleted-001` | holdout | L1 | L2 | — |
| `ho-py-unsafe-load-001` | holdout | L1 | — | — |
| `ho-sql-delete-all-001` | holdout | L1 | — | — |
| `ho-ts-constructor-001` | holdout | L1 | — | — |
| `ho-ts-method-001` | holdout | L1 | — | — |
| `ho-ts-neg-rename-001` (negative) | holdout | — | — | — |
| `ho-ts-new-function-001` | holdout | L1 | — | — |
| `js-error-001` | dev | L1 | — | — |
| `js-logic-001` | dev | L1 | — | — |
| `js-security-001` | dev | L1 | — | — |
| `json-deps-001` | dev | L1, L2, L3 | — | — |
| `py-async-001` | dev | L1 | — | — |
| `py-behavior-001` | dev | L1 | — | — |
| `py-breaking-001` | dev | L1 | — | — |
| `py-breaking-002` | dev | L1 | — | — |
| `py-breaking-003` | dev | L1 | — | — |
| `py-breaking-004` | dev | L1 | — | — |
| `py-coverage-001` | dev | L1 | — | — |
| `py-deps-001` | dev | L1, L2 | — | — |
| `py-error-001` | dev | L1 | — | — |
| `py-error-002` | dev | L1 | — | — |
| `py-logic-001` | dev | L1 | — | — |
| `py-logic-002` | dev | L1 | — | — |
| `py-migration-001` | dev | L1 | — | — |
| `py-neg-001` (negative) | dev | — | — | — |
| `py-neg-002` (negative) | dev | — | — | — |
| `py-neg-003` (negative) | dev | — | — | — |
| `py-secret-001` | dev | L1 | — | — |
| `py-security-001` | dev | L1, L2 | — | — |
| `py-security-002` | dev | L1 | — | — |
| `py-test-001` | dev | L1, L2 | — | — |
| `py-undefined-001` | dev | L1 | — | — |
| `sql-migration-001` | dev | L1 | — | — |
| `ts-async-001` | dev | L1 | — | — |
| `ts-breaking-001` | dev | L1 | — | — |
| `ts-breaking-002` | dev | L1 | — | — |
| `ts-neg-001` (negative) | dev | — | — | — |
| `ts-security-001` | dev | L1 | — | — |
| `ts-security-002` | dev | L1 | — | — |
| `ts-test-001` | dev | L1 | — | — |

## What this evaluation cannot establish

- The dataset is small and synthetic: each case was written for this project to exercise a specific risk pattern. Results measure agreement with the labelling guideline on these cases, not effectiveness on real repositories.
- The rules and the dev-split cases were written by the same author, so dev-split numbers are optimistic by construction. The holdout splits were written after the ruleset was frozen; their first runs, recorded before any holdout-informed change, are the more honest estimate, but they share the same author and style.
- Bootstrap intervals resample cases; with this few cases they are wide and should be read as rough bounds.
- Labels mark where a reviewer should look, not whether the change causes a production incident. Nothing here estimates incident probability.
- AI metrics measure grounding (cited evidence exists and matches) and agreement with labels. They do not measure the correctness or usefulness of explanations, which would require human rating.
