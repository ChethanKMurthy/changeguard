# Demo script (about 7 minutes)

Setup: `make dev` (or `docker compose up`), a browser at http://localhost:3000,
and optionally Ollama with `llama3.2:3b` for the AI segment
(`CHANGEGUARD_AI_PROVIDER=ollama CHANGEGUARD_AI_MODEL=llama3.2:3b make dev`).
The sample is synthetic; say so once, early.

## 1. The claim (30 s) · landing page

> "ChangeGuard reads a diff the way a careful reviewer does, and every finding
> shows how it was established."

Point at Fig. 1 replaying: a real run on the sample. Scroll to the provenance
ladder: deterministic, heuristic, and model-generated findings are kept apart.

## 2. Follow one change (3 min) · Experience

1. Fig. 1: press **Run it on your engine**. The pipeline streams live; the event
   log fills; the result strip says all finding IDs match the recording.
   > "Same input, same IDs. The engine is deterministic, so we can check that."
2. Chapter 01, Fig. 3: ask the audience what they would flag, then press **Show
   what ChangeGuard flagged**.
3. Chapter 03, Fig. 5: the two call sites that no longer bind. Read the caveat:
   the `"EUR"` call binds but is wrong.
   > "It tells you what it cannot see."
4. Chapter 04: the undefined name plus the bare `except` that swallows it.
5. Chapter 07: the model's verified note, and the free-text summary it is not
   shown because it misattributes a function.

## 3. A real report (1.5 min) · Analyse

1. **Analyse** → **Analyse sample**. Watch the stages, then the report opens.
2. Click the top finding: evidence cards with exact lines, the failure scenario,
   the suggested check.
3. **Export** → Markdown (for a PR comment) or SARIF (for code scanning).
4. Optional: paste a diff from your own repository.

## 4. Does it work? (1.5 min) · Evaluation

1. Start at the clean holdout results, not the headline: 83% / 75% on the first
   holdout's first run, and the fixes it forced.
2. The ablation: without the snapshot, recall drops from 94% to 72%.
3. The model section: grounding held for all three; the 7B model's extra risks
   were mostly wrong, which is why model findings are capped.
   > "The evaluation exists to show where it is weak, too."

## 5. Close (30 s) · Method

The rule catalogue (91 rules with rationales), the threat model, and the CI
command:

```bash
changeguard analyze --git-repo . --base origin/main --format sarif -o changeguard.sarif --fail-on high
```
