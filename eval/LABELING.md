# Labelling guide

This guide defines what a label means in the ChangeGuard evaluation dataset, so
that a case can be labelled without looking at what the tool reports. Every case
in `dataset/cases/` was labelled against it, and every correction made after a
run is governed by section 4.

## 1. What a label is

A **label** marks a place in a change where a careful reviewer should stop,
because the change as written can plausibly cause a defect, a security exposure,
a broken contract, or a loss of test protection. A label is *not* a claim that
the change will cause a production incident, and it carries no probability.

Each label has:

| Field      | Meaning |
|------------|---------|
| `id`       | `L1`, `L2`, … unique within the case. |
| `category` | One of the report categories (`breaking_change`, `security`, `logic_change`, `behavior_change`, `correctness`, `error_handling`, `concurrency`, `data_migration`, `dependency`, `secret_exposure`, `prompt_injection`, `test_integrity`, `coverage_gap`, …). Choose the category that describes the *consequence*, not the syntax. |
| `file`     | Repository-relative path of the line that needs attention. |
| `lines`    | `[start, end]` in the revision named by `side`. Point at the line a reviewer must read, not the whole function. |
| `side`     | `head` (default) for added or changed code, `base` for removed code (for example a deleted test). |
| `severity` | `critical`, `high`, `medium`, or `low`, judged by worst plausible consequence if the problem is real. Used only for the severity-agreement metric. |
| `note`     | Free text. Explain anything a second labeller would need. |

## 2. What to label

Label a location when **all** of the following hold:

1. The problem is introduced or exposed **by this change**. Pre-existing issues are not labelled.
2. A reviewer reading only the change and the repository could reasonably notice it.
3. The consequence is concrete: a call that will fail, input that takes a wrong branch, a credential that becomes readable, a test that no longer runs, a migration that destroys data.

Label one location per problem. When the same defect shows in several lines (a
removed parameter and its three stale callers), label the line where the fix
belongs and list the other lines as acceptable observations if useful.

**Negative controls** are changes a careful reviewer would approve without
comment: pure refactors, safe renames with updated callers, test additions,
documentation. They carry no labels; any finding on them is a false positive.

## 3. Acceptable observations

Some findings are true but secondary: a changed function with no direct test, a
complexity increase, a debug print. They are worth seeing but not required. List
them under `acceptable` with a `category` and, optionally, `file` and `lines`.

A prediction that matches an acceptable entry, or that is a second prediction on
an already-matched label, is counted as **neither** a true nor a false positive.

## 4. Corrections

Labels are written before a case is first evaluated, and a holdout case is
evaluated exactly once before anything can change. After that run:

- A label may be corrected **only** when it violates this guide as written: a
  wrong line, a wrong file, a category that contradicts section 1, or an
  acceptable observation that section 3 requires and the author omitted.
- A label is never changed to agree with tool output, and never removed because
  a system misses it.
- Every correction is recorded in `reports/holdout-history.json` under
  `changes_after` for that split, with the case ID and the reason, and noted in
  the case's own `note` field.
- Numbers reported for a split after a correction are not clean estimates. The
  first-run numbers stay published next to them.

## 5. Matching rule used by the harness

A prediction matches a label when the category and file are equal and the line
ranges overlap after widening the label by ±3 lines. Matching is one-to-one: a
label can absorb at most one prediction. Precision and recall are micro-averaged
over all labels; confidence intervals are percentile bootstrap intervals over
cases.

## 6. Writing a new case

1. Create `dataset/cases/<id>/base/` with the repository before the change and
   `head/` with the repository after it.
2. Generate the patch: `uv run python tools/make_patch.py <case dir>` (from `backend/`).
3. Write `case.yaml` with labels from sections 1–3 **before** running any system.
4. New cases belong to the next unused split if they are meant as a holdout:
   record the first run's raw console output under `reports/runs/` and add the
   result to `reports/holdout-history.json`.
