import type { StageResult } from "./api/types";

export type StageStatus = "pending" | "running" | "ok" | "skipped" | "warning" | "failed";

export interface StageView {
  name: string;
  label: string;
  status: StageStatus;
  durationMs?: number;
  detail?: string;
  notes?: string[];
}

export const STAGES: { name: string; label: string; does: string; never?: string }[] = [
  { name: "ingest", label: "Parse inputs", does: "Validates and parses the patch, snapshot archive, and coverage report.", never: "Never extracts archives to disk or follows symlinks." },
  { name: "workspace", label: "Reconstruct revisions", does: "Applies the patch to the snapshot in memory to rebuild the base and head revisions.", never: "Never runs git hooks or repository scripts." },
  { name: "structure", label: "Structural diff", does: "Parses both revisions with tree-sitter and diffs functions, classes, and signatures." },
  { name: "references", label: "Cross-file references", does: "Resolves imports and finds every caller of a changed symbol, then checks each call against the new signature." },
  { name: "static", label: "Static analysis", does: "Runs Ruff on both revisions and keeps only diagnostics the change introduced.", never: "Never executes the analysed code." },
  { name: "rules", label: "Risk rules", does: "Secrets, injection sinks, migrations, dependencies, condition flips, and test-integrity rules on added lines." },
  { name: "tests", label: "Test mapping", does: "Finds tests that import and exercise each changed symbol." },
  { name: "coverage", label: "Coverage", does: "Measures which changed lines the uploaded coverage report says never ran." },
  { name: "synthesis", label: "AI synthesis", does: "Optional: a model explains findings and proposes risks, citing evidence IDs only.", never: "Never sees secrets or prompt-injection text." },
  { name: "verification", label: "Grounding verification", does: "Rejects any model claim whose evidence, paths, lines, or numbers do not check out." },
  { name: "report", label: "Assemble report", does: "De-duplicates findings, verifies every evidence reference, and computes the review priority." },
];

function n(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

/** One-line, human summary of a completed stage, from its structured summary. */
export function stageDetail(stage: Pick<StageResult, "name" | "summary" | "status" | "notes">): string | undefined {
  const s = stage.summary ?? {};
  if (stage.status === "skipped") return stage.notes?.[0];
  switch (stage.name) {
    case "ingest":
      return `${n(s.files)} file${n(s.files) === 1 ? "" : "s"} · +${n(s.additions)} −${n(s.deletions)}${s.snapshot_files ? ` · ${n(s.snapshot_files)}-file snapshot` : ""}`;
    case "workspace":
      return s.mode === "full_context" ? `Full context · ${n(s.repository_files)} repository files` : "Diff only · no snapshot";
    case "structure":
      return `${n(s.changed_symbols)} symbols changed · ${n(s.breaking)} breaking`;
    case "references":
      return `${n(s.call_sites_checked)} call sites checked · ${n(s.incompatible)} incompatible`;
    case "static":
      return s.skipped ? String(s.skipped) : `${n(s.new_diagnostics)} new diagnostics${s.tool ? ` · ${String(s.tool)}` : ""}`;
    case "rules": {
      let total = 0;
      for (const group of Object.values(s)) {
        if (group && typeof group === "object") for (const v of Object.values(group as Record<string, unknown>)) total += n(v);
      }
      return `${total} rule match${total === 1 ? "" : "es"}`;
    }
    case "tests":
      return `${n(s.with_tests)} of ${n(s.testable_symbols)} changed symbols have tests`;
    case "coverage":
      return s.patch_coverage_percent != null
        ? `Patch coverage ${s.patch_coverage_percent}% · ${n(s.changed_covered_lines)}/${n(s.changed_executable_lines)} lines`
        : "No changed executable lines matched";
    case "synthesis":
      return s.model ? `${String(s.model)} · ${n(s.calls)} call${n(s.calls) === 1 ? "" : "s"} · ${n(s.input_tokens)}→${n(s.output_tokens)} tokens` : stage.notes?.[0];
    case "verification":
      return `${n(s.accepted)} of ${n(s.claims)} claims verified${n(s.rejected) ? ` · ${n(s.rejected)} rejected` : ""}`;
    case "report":
      return `${n(s.findings)} findings · ${n(s.evidence)} evidence items`;
    default:
      return undefined;
  }
}

export function initialStages(): StageView[] {
  return STAGES.map((s) => ({ name: s.name, label: s.label, status: "pending" }));
}

export function stagesFromResults(results: StageResult[]): StageView[] {
  const byName = new Map(results.map((r) => [r.name, r]));
  return STAGES.map((s) => {
    const r = byName.get(s.name);
    if (!r) return { name: s.name, label: s.label, status: "pending" as const };
    return { name: s.name, label: s.label, status: r.status, durationMs: r.duration_ms, detail: stageDetail(r), notes: r.notes };
  });
}
