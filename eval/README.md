# Evaluation

Labelled code changes and the harness that scores ChangeGuard against them.

```
eval/
├── dataset/cases/<id>/    case.yaml, base/, head/, change.patch, [coverage report]
├── recordings/            recorded model responses, one JSON file per request fingerprint
├── baselines/             committed results the CI regression gate compares against
├── reports/
│   ├── latest.json        full results of the last run (all systems, per-case details)
│   ├── latest.md          the same, as a readable report
│   ├── holdout-history.json   clean first-run results per holdout split, and what changed after
│   └── runs/              raw console output of each holdout's first run
├── LABELING.md            what a label means; how corrections are allowed
└── DATASHEET.md           what is in the dataset, how it was made, what it is not for
```

## Run it

From `backend/`:

```bash
# Rules, the diff-only ablation, and two naive baselines (seconds, no model):
uv run changeguard eval

# Add the recorded language-model systems (replayed, no model needed):
uv run changeguard eval --ai replay --ai-model "llama3.2:3b,qwen2.5-coder:7b,qwen2.5-coder:7b@3"

# Gate on the committed baseline, as CI does:
uv run changeguard eval --ai replay \
  --ai-model "llama3.2:3b,qwen2.5-coder:7b,qwen2.5-coder:7b@3" \
  --check-baseline ../eval/baselines/changeguard.json
```

A run writes `reports/latest.{json,md}` and the web app's
`frontend/src/data/evaluation.json` (skip with `--no-write`). `--split holdout`
evaluates one split.

## Recording model responses

`--ai record` calls the model and stores each response under
`recordings/<provider>-<model>/<request sha256>.json`; `--ai replay` serves them
back and fails loudly on any request it has not seen (a "replay miss"). Because
the request fingerprint covers the prompt, the evidence pack, and the decoding
settings, any change to the rules or the prompt that alters what the model sees
requires re-recording. `model@k` runs k-sample self-consistency.

```bash
ollama pull qwen2.5-coder:7b
uv run changeguard eval --ai record --ai-model qwen2.5-coder:7b
```

## Metrics

- **Precision / recall / F1**, micro-averaged over labels, with one-to-one
  matching (same category and file, line ranges overlapping within ±3 lines).
- **95% bootstrap intervals** over cases (2,000 resamples, fixed seed), overall
  and per split.
- **Negative-control false-alarm rate**: the share of safe changes with at least
  one finding.
- **Unsupported evidence**: findings whose cited evidence fails an independent
  re-check against the case files (must be zero).
- **Precision by provenance and by confidence**, and **severity agreement** on
  matched findings.
- For model systems: claims made and rejected (with reasons), notes attached,
  model-proposed findings and how many matched a label, latency, and tokens.

## Baselines and ablation

- `baseline-keyword` flags added lines containing risky-looking tokens.
- `baseline-changed-symbols` flags every changed function, and every signature
  change as breaking.
- `changeguard-diff-only` runs the same rules without the repository snapshot,
  which isolates what cross-file analysis contributes.

Results and their caveats are summarised in [`../docs/EVALUATION.md`](../docs/EVALUATION.md)
and on the web app's Evaluation page.
