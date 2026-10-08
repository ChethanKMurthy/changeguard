# Product

## Register

product

## Users

- **Reviewers and authors of code changes** (primary). A developer about to merge a pull request, or a reviewer deciding whether to approve one. They have a diff open, limited time, and one question: *what could this break, and how do I know?* They read evidence line by line and need to trust every number on the screen.
- **Technical evaluators** (secondary). Hiring managers and engineers assessing the project as a portfolio piece. They arrive on the landing page or the guided Experience, have a few minutes, and judge engineering judgement, honesty about limitations, and craft.

## Product Purpose

ChangeGuard analyses a code change (a git diff, optionally with a repository snapshot and a coverage report) and produces a structured risk report. Every finding cites evidence extracted from the inputs, states severity and confidence separately, and says whether it came from deterministic analysis, a heuristic rule, or a language model that was checked against that evidence.

Success: a reviewer finds the real risk in a change faster than reading the diff alone, and never has to wonder whether a claim was made up.

## Brand Personality

**Calibrated, forensic, lucid.** The voice of a lab report: precise, unhurried, plainly worded, never hyped. It states what was measured and what was not. Confidence comes from showing the evidence, not from adjectives. The emotional goal is trust: "this tool knows exactly how sure it is."

Visual reference points (for qualities, not looks): a calibration certificate (every reading traceable to an instrument), a forensic evidence label (chain of custody), a scientific figure plate (data as the image, captions that explain).

## Anti-references

- A generic AI chatbot or "copilot" chat panel. ChangeGuard is not a conversation.
- Superficial AI dashboards: hero metrics with gradient accents, fake "risk scores" shown as percentages, glowing purple AI sparkle everywhere.
- SaaS landing-page templates: identical feature-card grids, eyebrow labels above every section, testimonial carousels.
- Editorial-magazine affectation (italic display serifs, drop caps, broadsheet columns). This is an instrument, not a magazine.
- Security-tool fear marketing: red alarm palettes, skulls, "threat" imagery.

## Design Principles

1. **Evidence before assertion.** Every claim on screen links to the evidence that supports it, one click away. If something can't be supported, it isn't shown.
2. **Provenance is always visible.** Deterministic, heuristic, and AI-generated content are visually distinct everywhere they appear, by shape as well as colour.
3. **Calibrated, not alarming.** Severity and confidence are separate and categorical. No invented probabilities, no alarm theatre. Calm presentation of serious findings.
4. **Show the instrument.** The pipeline, the checks, the model calls, and the evaluation are part of the product. Make the machinery legible instead of hiding it behind a single verdict.
5. **Honest limits.** Unsupported modes, skipped stages, and evaluation caveats are stated where they matter, in plain language.

## Accessibility & Inclusion

- WCAG 2.2 AA: body text ≥ 4.5:1, large text and UI glyphs ≥ 3:1, visible focus on every interactive element, full keyboard operation of filters, tabs, and the finding inspector.
- Severity and provenance never rely on colour alone (shape glyphs + text labels).
- `prefers-reduced-motion` honoured everywhere: animations become cross-fades or instant state changes; no content is gated on an animation completing.
- Light and dark themes, following the system preference with a manual override.
