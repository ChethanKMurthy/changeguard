# System card

A summary of what ChangeGuard is for, how its optional language model is used and
constrained, and how it was evaluated. The web app's Method page presents the
same information with the full rule catalogue.

## Intended use

**For:** pointing code reviewers at the lines of a change that most need
attention, with evidence; catching mechanical breakage (callers that no longer
bind, removed symbols still referenced, new lint errors); showing which changed
lines no test executed; gating CI on deterministic and heuristic findings.

**Not for:** deciding that a change is safe (an empty report means no rule
matched); estimating incident probability; replacing tests, type checking, or a
human reading the change for meaning.

## Components

| Component | Role | Can it be wrong? |
|-----------|------|------------------|
| Deterministic analysis (◆) | Parses, resolves calls, measures lines | Only if parsing or resolution is wrong; evidence makes this checkable |
| Heuristic rules (◇) | Patterns worth attention | Yes, by design; confidence is stated |
| Language model (✦, optional) | Explains findings, proposes risks | Yes; verified for grounding, capped, labelled |

## The model

- **Providers:** Ollama (local, free), any OpenAI-compatible server, or the Claude
  API (`claude-opus-5-5` by default; opt-in and billed). Off by default. Only
  Ollama has been exercised end to end; the hosted adapters are tested against
  mocked clients.
- **Input:** a fenced evidence pack (findings, evidence excerpts, change summary),
  up to 8 findings and 24,000 characters. Secrets are masked first; lines flagged
  as prompt injection are withheld.
- **Output:** a closed JSON schema. Notes on existing findings, and additional
  risks with category, severity (at most high) and confidence (at most medium).
  No file or line fields: locations come from cited evidence.
- **Verification:** every claim must cite evidence that exists; paths must belong
  to the change; line numbers must fall inside cited evidence; named functions
  must appear in it; percentages must appear in it; no claim may report a test
  result. Failing claims are rejected with reasons, never repaired.
- **Display:** notes appear beside the rule's analysis. Model findings are
  labelled, confidence-capped, can raise review priority at most to Elevated,
  and never fail CI. Free-text summaries are not displayed.
- **Traceability:** prompt ID, version and SHA-256; per-call request hash,
  latency, tokens, attempts, cache hit; rejected claims with reasons.

## Evaluation summary

On the labelled dataset (small, synthetic, same author as the rules):

| System | Precision | Recall | False alarms on safe changes |
|--------|-----------|--------|------------------------------|
| Rules only | 100.0% | 93.8% | 0/9 |
| Rules, first runs on the two holdouts | 83.3% / 100.0% | 75.0% / 81.8% | 2/3 / 0/2 |
| + llama3.2:3b | 98.4% | 93.8% | 0/9 |
| + qwen2.5-coder:7b | 53.4% | 96.9% | 9/9 |
| + qwen2.5-coder:7b, 3-sample vote | 65.0% | 96.9% | 7/9 |

No system cited unsupported evidence. Details and caveats:
[EVALUATION.md](EVALUATION.md).

## Known failure modes

- Misattribution in free text (a recorded summary placed a condition change in
  the wrong function); such text is not displayed.
- Plausible, grounded, wrong risks, at a high rate for the 7B model.
- Context trimming on large changes.
- Semantic regressions that neither rules nor small models reliably catch.

## Data

Reports store the diff hunks, cited excerpts and findings, not the repository.
Archives and coverage files are discarded after analysis. With a hosted model,
the redacted evidence pack goes to that provider. No telemetry.
