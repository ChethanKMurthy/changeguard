# Design

> Visual system for ChangeGuard. Strategy lives in [PRODUCT.md](PRODUCT.md). Tokens are defined in
> `frontend/src/app/globals.css`; this document explains the intent behind them.

## Visual theme

**"Instrument report."** A calibration lab's bench under clean daylight: white surfaces, near-black ink,
and amber indicator glass that lights up where attention is needed. The product is an instrument; the
landing page and the Experience are its demonstration, so they use the same vocabulary at a larger scale
rather than a separate marketing look.

Signature motifs (each carries meaning, none is decoration):

- **Provenance glyphs** — `◆` deterministic (solid: established fact), `◇` heuristic (hollow: inferred),
  `✦` AI-generated (spark: proposed by a model and verified). Used identically in the report, the
  Experience, the evaluation, and the landing page.
- **Evidence tags** — evidence IDs (`E3`) render as small monospaced specimen tags. Anything tagged can
  be opened to its verbatim source.
- **Signal trace** — a thin amber line that travels through the pipeline diagram, representing a change
  moving through the stages. It only appears where something is actually flowing.

## Color

Strategy: **Restrained** on product surfaces (report, workspace, history), **Committed** moments on the
landing page and Experience (the amber signal carries the hero's pipeline and the evaluation band).
All colors are OKLCH.

| Role | Light | Dark | Use |
|---|---|---|---|
| `bg` | `oklch(1 0 0)` | `oklch(0.13 0 0)` | page |
| `surface` | `oklch(0.973 0.003 60)` | `oklch(0.172 0.004 60)` | panels, code |
| `surface-2` | `oklch(0.945 0.004 60)` | `oklch(0.215 0.005 60)` | inset wells, hover |
| `ink` | `oklch(0.205 0.012 50)` | `oklch(0.94 0.006 70)` | text, primary actions |
| `muted` | `oklch(0.47 0.012 55)` | `oklch(0.72 0.01 65)` | secondary text (≥ 4.5:1) |
| `line` | `oklch(0.90 0.004 60)` | `oklch(0.29 0.006 60)` | hairlines |
| `signal` | `oklch(0.47 0.14 48)` | `oklch(0.78 0.15 64)` | amber: attention, active stage, focus |
| `signal-glow` | `oklch(0.72 0.16 62)` | `oklch(0.80 0.15 66)` | traces and indicator lights |
| `ai` | `oklch(0.47 0.085 205)` | `oklch(0.78 0.09 198)` | verdigris: model-generated content |

Severity (data semantics, used for small markers and the left edge of nothing — never stripes):
critical `oklch(0.50 0.19 27)`, high `oklch(0.60 0.17 45)`, medium `oklch(0.72 0.14 85)`,
low `oklch(0.58 0.07 245)`, info `oklch(0.62 0.01 60)`. Severity is always paired with a text label.

Text on saturated fills is white. Tinted badges use a pale fill (L ≥ 0.94) with the strong colour as text.

## Typography

- **Archivo** (variable `wght` + `wdth`). One family carries the whole system: expanded width
  (`wdth` 112–125) for display headlines, normal width for UI and prose. Chosen for its engineered,
  instrument-panel character without being a costume.
- **Martian Mono** (variable) for code, evidence excerpts, IDs, and numeric readouts only.
- Product surfaces use a fixed rem scale (ratio ~1.2). The landing page and Experience use fluid
  `clamp()` headings capped at 5.5rem, letter-spacing no tighter than -0.035em, `text-wrap: balance`.
- Prose is capped at 68ch.

## Layout

- 12-column grid, max content width 1240px, 16px gutters on mobile.
- Product surfaces: dense, scannable, inspector pattern (list on the left, evidence on the right) on
  desktop; the inspector becomes a full-height sheet on mobile.
- Brand surfaces: one dominant idea per viewport, long scroll, figure plates with captions.
- Radii: 6px controls, 10px panels. Shadows only for floating layers.
- z-index scale: dropdown 20, sticky 30, overlay 40, sheet 50, toast 60, tooltip 70.

## Components

Buttons (ink filled primary, outline secondary, ghost tertiary), segmented filters, provenance and
severity badges, evidence tags, code excerpts with highlighted lines, unified diff viewer with
annotation markers, stage timeline, charts with confidence-interval whiskers. Every interactive
component has hover, focus-visible, active, disabled, and loading states.

## Motion

- Product: 160–220 ms state transitions, `cubic-bezier(0.22, 1, 0.36, 1)` (ease-out-quint). Motion only
  conveys state: a stage completing, a filter re-flowing the list, an inspector opening.
- Brand: one orchestrated hero sequence (the signal trace running through the pipeline), scroll-linked
  figure changes in the Experience, chart bars that draw once when first visible.
- Route changes cross-fade with React `<ViewTransition>`.
- `prefers-reduced-motion`: all of the above become instant or opacity-only.
