# ChangeGuard report — Sample: A pricing refactor that quietly breaks its callers

> **Review priority: HIGH** — 2 high-severity deterministic or heuristic finding(s).
> Severity and confidence are categorical rule judgements, not probabilities of failure.

| | |
|---|---|
| Files changed | 3 (+24 −5) — Python |
| Mode | Full context (repository snapshot) |
| Findings | 13 — deterministic 9 · heuristic 4 · AI 0 |
| Changed symbols | 5 (1 with breaking signature changes) |
| Patch coverage | 21.1% (4/19 changed executable lines, from uploaded report) |
| AI synthesis | completed — ollama / llama3.2:3b; 2/2 claims passed grounding checks |
| Engine | ChangeGuard 0.1.0 · ruleset 2026.10.4 · report schema 1.0 |

## Findings

### 1. [HIGH] 2 call site(s) incompatible with new signature of `format_price`
`CG-API-001` · deterministic · confidence high · `src/billing/pricing.py:16`

`format_price` changed (parameter `currency` removed; required parameter `locale` added). 2 of 3 call site(s) in the repository no longer match the new signature.

**Why it matters.** A caller still uses the old calling convention. In Python this raises TypeError at call time; in TypeScript it fails compilation.

**Failure scenario.** src/billing/invoice.py:9 still calls `format_price` the old way: it passes unexpected keyword argument `currency`. Python raises TypeError when that line runs.

**Evidence**

- **E2** Signature of format_price changed — `src/billing/pricing.py:16` _(source: tree-sitter structural diff)_

  ```python

  def format_price(amount: Decimal, locale: str) -> str:
      """Render an amount using the symbol for the caller's locale."""
  ```
- **E3** Call site src/billing/invoice.py:9 in render_line — `src/billing/invoice.py:9` _(source: repository snapshot (tree-sitter))_

  ```python
  def render_line(description: str, amount: Decimal, currency: str) -> str:
      return f"{description}: {format_price(amount, currency=currency)}"

  ```
- **E4** Call site tests/test_pricing.py:18 in test_format_price_defaults_to_usd — `tests/test_pricing.py:18` _(source: repository snapshot (tree-sitter))_

  ```python
  def test_format_price_defaults_to_usd():
      assert format_price(Decimal("5")) == "$5.00"
      assert format_price(Decimal("5"), "EUR") == "€5.00"
  ```

**Suggested regression check.** Update the incompatible callers, then add a regression test that calls `format_price` the way those callers do.

```python
from billing.pricing import format_price


def test_format_price_matches_callers():
    # mirror the argument shape used at the call sites listed in the evidence
    result = format_price(amount=..., locale=...)
    assert result == ...  # expected value for these inputs
```

<details><summary>AI analysis (llama3.2:3b, passed grounding checks, confidence high)</summary>

The new signature of `format_price` changes the required parameter from `currency` to `locale`, making it incompatible with existing call sites.

_Failure scenario:_ A function calls `format_price` with a `currency` argument, but the function is expecting a `locale` argument. This will cause a TypeError when trying to execute the function.

_Uncertainty:_ low

</details>

### 2. [HIGH] Undefined name `REGIONAL_RATES`
`RUFF-F821` · deterministic · confidence high · `src/billing/pricing.py:27`

Undefined name `REGIONAL_RATES` (Ruff F821) in `total_with_tax`. This diagnostic is new in the head revision.

**Why it matters.** Undefined name: raises NameError when the line executes.

**Failure scenario.** When `total_with_tax` runs, line 27 raises NameError.

**Evidence**

- **E7** Ruff F821 at src/billing/pricing.py:27 — `src/billing/pricing.py:27` _(source: ruff (ruff 0.16.10))_

  ```python
          return subtotal * (1 + TAX_RATE)
      try:
          return subtotal * REGIONAL_RATES[region]
      except:
          pass
  ```

**Suggested unit check.** Add a unit test that executes `total_with_tax` (line 27); it fails immediately while this diagnostic is present.

### 3. [MEDIUM] No test executes src/billing/api.py (3 changed executable line(s))
`CG-COV-001` · deterministic · confidence high · `src/billing/api.py:4-13`

The coverage report records 0 hits for every one of the 10 executable lines in src/billing/api.py, including the changed line(s) 4, 11, 13. The module is probably never imported by a test.

**Why it matters.** The uploaded coverage report marks these changed executable lines as never executed by the test suite.

**Failure scenario.** Any bug introduced in this file reaches production without a single test running its code.

**Evidence**

- **E14** src/billing/api.py is never executed by the test suite — `src/billing/api.py:4` _(source: coverage report (cobertura))_

  ```python
  import time

  from billing.invoice import invoice_total


  async def handle_invoice(request_body: str) -> dict[str, str]:
      payload = json.loads(request_body)
      time.sleep(0.05)  # crude rate limiting
      total = invoice_total(payload["items"], payload.get("discount", 0), payload["region"])
      print("invoice total", total)
  ```

**Suggested unit check.** Add a test module that imports src/billing/api.py and exercises the changed code paths.

### 4. [MEDIUM] Async functions should not call `time.sleep`
`RUFF-ASYNC251` · deterministic · confidence high · `src/billing/api.py:11`

Async functions should not call `time.sleep` (Ruff ASYNC251) in `handle_invoice`. This diagnostic is new in the head revision.

**Why it matters.** time.sleep inside async function blocks the event loop.

**Failure scenario.** Under load, `handle_invoice` blocks the event loop and stalls every concurrent request.

**Evidence**

- **E5** Ruff ASYNC251 at src/billing/api.py:11 — `src/billing/api.py:11` _(source: ruff (ruff 0.16.10))_

  ```python
  async def handle_invoice(request_body: str) -> dict[str, str]:
      payload = json.loads(request_body)
      time.sleep(0.05)  # crude rate limiting
      total = invoice_total(payload["items"], payload.get("discount", 0), payload["region"])
      print("invoice total", total)
  ```

**Suggested integration check.** Exercise `handle_invoice` under asyncio debug mode (PYTHONASYNCIODEBUG=1) and assert no slow-callback warnings; switch to the async equivalent of the blocking call.

### 5. [MEDIUM] No test executes src/billing/loyalty.py (8 changed executable line(s))
`CG-COV-001` · deterministic · confidence high · `src/billing/loyalty.py:1-11`

The coverage report records 0 hits for every one of the 8 executable lines in src/billing/loyalty.py, including the changed line(s) 1, 3, 6–11. The module is probably never imported by a test.

**Why it matters.** The uploaded coverage report marks these changed executable lines as never executed by the test suite.

**Failure scenario.** Any bug introduced in this file reaches production without a single test running its code.

**Evidence**

- **E15** src/billing/loyalty.py is never executed by the test suite — `src/billing/loyalty.py:1` _(source: coverage report (cobertura))_

  ```python
  """Loyalty programme bonuses."""

  from decimal import Decimal


  def loyalty_bonus(years: int, tier: str) -> Decimal:
      if tier == "gold" and years > 3:
          return Decimal("0.05")
      if tier == "silver":
          return Decimal("0.02")
      return Decimal("0")
  ```

**Suggested unit check.** Add a test module that imports src/billing/loyalty.py and exercises the changed code paths.

### 6. [MEDIUM] 3 of 3 changed executable line(s) in `total_with_tax` never run in tests
`CG-COV-001` · deterministic · confidence high · `src/billing/pricing.py:27-29`

The coverage report shows 0 hits for changed line(s) 27–29 of src/billing/pricing.py.

**Why it matters.** The uploaded coverage report marks these changed executable lines as never executed by the test suite.

**Failure scenario.** A bug on line 27 would not fail any existing test, because the test suite never executes it.

**Evidence**

- **E17** Uncovered changed lines in total_with_tax — `src/billing/pricing.py:27` _(source: coverage report (cobertura))_

  ```python
      try:
          return subtotal * REGIONAL_RATES[region]
      except:
          pass
      return subtotal
  ```

**Suggested unit check.** Add a test that drives execution through line(s) 27–29 of src/billing/pricing.py, then re-run coverage to confirm.

### 7. [MEDIUM] Do not use bare `except`
`RUFF-E722` · deterministic · confidence high · `src/billing/pricing.py:28` · corroborated by `RUFF-S110`

Do not use bare `except` (Ruff E722) in `total_with_tax`. This diagnostic is new in the head revision.

**Why it matters.** Bare except also catches SystemExit and KeyboardInterrupt.

**Failure scenario.** A failure inside `total_with_tax` is swallowed; the caller proceeds with missing or partial results.

**Evidence**

- **E8** Ruff E722 at src/billing/pricing.py:28 — `src/billing/pricing.py:28` _(source: ruff (ruff 0.16.10))_

  ```python
      try:
          return subtotal * REGIONAL_RATES[region]
      except:
          pass
      return subtotal
  ```
- **E9** Ruff S110 at src/billing/pricing.py:28 — `src/billing/pricing.py:28` _(source: ruff (ruff 0.16.10))_

  ```python
      try:
          return subtotal * REGIONAL_RATES[region]
      except:
          pass
      return subtotal
  ```

**Suggested unit check.** Add a test that makes the guarded call in `total_with_tax` raise, and assert the error is surfaced (logged or re-raised) rather than swallowed.

### 8. [MEDIUM] No tests reference changed `handle_invoice`
`CG-TST-001` · heuristic · confidence medium · `src/billing/api.py:9-14`

No test in the repository imports `src/billing/api.py` and references `handle_invoice`. 2 changed line(s) in this function are not verified by a directly related test.

**Why it matters.** No test in the snapshot imports and references the changed symbol, so a regression may go undetected. Tests that exercise it indirectly are not detected.

**Failure scenario.** A regression in `handle_invoice` ships unnoticed because CI has no test that targets it.

**Evidence**

- **E11** Modified function handle_invoice — `src/billing/api.py:9` _(source: repository snapshot)_

  ```python
  async def handle_invoice(request_body: str) -> dict[str, str]:
      payload = json.loads(request_body)
      time.sleep(0.05)  # crude rate limiting
      total = invoice_total(payload["items"], payload.get("discount", 0), payload["region"])
      print("invoice total", total)
      return {"total": str(total)}
  ```

**Suggested unit check.** Add focused tests for `handle_invoice` (e.g. in tests/test_api.py) covering the changed lines.

```python
from billing.api import handle_invoice

import pytest


@pytest.mark.asyncio
async def test_handle_invoice_behaviour():
    # cover the changed lines; add one case per branch you touched
    result = await handle_invoice(request_body=...)
    assert result == ...  # expected value for these inputs
```

### 9. [MEDIUM] No tests reference new `loyalty_bonus`
`CG-TST-001` · heuristic · confidence medium · `src/billing/loyalty.py:6-11`

No test in the repository imports `src/billing/loyalty.py` and references `loyalty_bonus`. 6 changed line(s) in this function are not verified by a directly related test.

**Why it matters.** No test in the snapshot imports and references the changed symbol, so a regression may go undetected. Tests that exercise it indirectly are not detected.

**Failure scenario.** A regression in `loyalty_bonus` ships unnoticed because CI has no test that targets it.

**Evidence**

- **E12** Added function loyalty_bonus — `src/billing/loyalty.py:6` _(source: repository snapshot)_

  ```python
  def loyalty_bonus(years: int, tier: str) -> Decimal:
      if tier == "gold" and years > 3:
          return Decimal("0.05")
      if tier == "silver":
          return Decimal("0.02")
      return Decimal("0")
  ```

**Suggested unit check.** Add focused tests for `loyalty_bonus` (e.g. in tests/test_loyalty.py) covering the changed lines.

```python
from billing.loyalty import loyalty_bonus


def test_loyalty_bonus_behaviour():
    # cover the changed lines; add one case per branch you touched
    result = loyalty_bonus(years=..., tier=...)
    assert result == ...  # expected value for these inputs
```

### 10. [MEDIUM] Condition logic changed: `>` → `>=`
`CG-LOG-001` · heuristic · confidence medium · `src/billing/pricing.py:11`

Line 11 in `apply_discount` changed only in `>` → `>=`; the condition's boundary or polarity is different now.

**Why it matters.** A comparison/boolean operator or negation changed. Boundary behaviour differs, which is a classic source of off-by-one and inverted-condition bugs.

**Failure scenario.** Inputs exactly at the boundary (or on the side the condition now excludes/includes) take the other branch than before — the classic off-by-one / inverted-condition regression.

**Evidence**

- **E10** Condition changed at src/billing/pricing.py:11 — `src/billing/pricing.py:11` _(source: diff)_

  ```diff
  -    if percent > 50:
  +    if percent >= 50:
  ```

**Suggested unit check.** Add boundary-value tests: the threshold itself, one below, and one above, asserting the intended branch for each.

### 11. [MEDIUM] No tests reference changed `total_with_tax`
`CG-TST-001` · heuristic · confidence medium · `src/billing/pricing.py:22-30`

No test in the repository imports `src/billing/pricing.py` and references `total_with_tax`. 4 changed line(s) in this function are not verified by a directly related test.

**Why it matters.** No test in the snapshot imports and references the changed symbol, so a regression may go undetected. Tests that exercise it indirectly are not detected.

**Failure scenario.** A regression in `total_with_tax` ships unnoticed because CI has no test that targets it.

**Evidence**

- **E13** Modified function total_with_tax — `src/billing/pricing.py:22` _(source: repository snapshot)_

  ```python
  def total_with_tax(subtotal: Decimal, region: str) -> Decimal:
      """Add sales tax for regions that charge it."""
      if region == "EU":
          return subtotal * (1 + TAX_RATE)
      try:
          return subtotal * REGIONAL_RATES[region]
      except:
          pass
      return subtotal
  ```

**Suggested unit check.** Add focused tests for `total_with_tax` (e.g. in tests/test_pricing.py) covering the changed lines.

```python
from billing.pricing import total_with_tax


def test_total_with_tax_behaviour():
    # cover the changed lines; add one case per branch you touched
    result = total_with_tax(subtotal=..., region=...)
    assert result == ...  # expected value for these inputs
```

### 12. [LOW] 1 of 2 changed executable line(s) in `format_price` never run in tests
`CG-COV-001` · deterministic · confidence high · `src/billing/pricing.py:18`

The coverage report shows 0 hits for changed line(s) 18 of src/billing/pricing.py.

**Why it matters.** The uploaded coverage report marks these changed executable lines as never executed by the test suite.

**Failure scenario.** A bug on line 18 would not fail any existing test, because the test suite never executes it.

**Evidence**

- **E16** Uncovered changed lines in format_price — `src/billing/pricing.py:18` _(source: coverage report (cobertura))_

  ```python
      """Render an amount using the symbol for the caller's locale."""
      symbol = {"en_US": "$", "de_DE": "€", "en_GB": "£"}.get(locale, "")
      return f"{symbol}{amount:.2f}"
  ```

**Suggested unit check.** Add a test that drives execution through line(s) 18 of src/billing/pricing.py, then re-run coverage to confirm.

### 13. [LOW] `print` found
`RUFF-T201` · deterministic · confidence medium · `src/billing/api.py:13`

`print` found (Ruff T201) in `handle_invoice`. This diagnostic is new in the head revision.

**Why it matters.** print() left in non-test code.

**Failure scenario.** `handle_invoice` emits debug output or pauses in production.

**Evidence**

- **E6** Ruff T201 at src/billing/api.py:13 — `src/billing/api.py:13` _(source: ruff (ruff 0.16.10))_

  ```python
      time.sleep(0.05)  # crude rate limiting
      total = invoice_total(payload["items"], payload.get("discount", 0), payload["region"])
      print("invoice total", total)
      return {"total": str(total)}
  ```

**Suggested static check.** Remove the debug statement; enable Ruff T10/T20 in CI.

## Limitations
- Static, name-based reference resolution: dynamic dispatch, reflection, monkey-patching, and dependency injection are not followed.
- Severity and confidence are categorical judgements defined per rule; they are not calibrated probabilities of a production incident.
- Test mapping detects tests that import and reference a changed symbol; tests that exercise it indirectly are not counted.
- ChangeGuard never executes code or tests; coverage numbers come only from an uploaded report.

<sub>Generated by ChangeGuard 0.1.0 · analysis `sample-billing-refactor-ai` · 2026-10-08T00:00:00Z</sub>
