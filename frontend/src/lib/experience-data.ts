import "server-only";

import type { Evidence, FileSummary, Finding, Report, SymbolChangeSummary } from "./api/types";
import { stagesFromResults, type StageView } from "./stages";
import { sampleMeta, sampleReport, sampleReportAI } from "./static-data";

/**
 * Slim, typed views of the recorded sample run for the guided experience.
 * Every number on the page is read from these reports; nothing is typed in by hand.
 */

export interface RecordedRun {
  analysisId: string;
  engine: string;
  ruleset: string;
  stages: StageView[];
  totalMs: number;
  findings: number;
  findingIds: string[];
  priority: string;
  bySeverity: Record<string, number>;
}

export interface SlimFinding {
  id: string;
  rule_id: string;
  title: string;
  severity: Finding["severity"];
  kind: Finding["kind"];
  confidence: Finding["confidence"];
  category: Finding["category"];
  file: string;
  line: number | null;
  evidence_ids: string[];
  corroborated_by: string[];
}

export function slim(f: Finding): SlimFinding {
  return {
    id: f.id,
    rule_id: f.rule_id,
    title: f.title,
    severity: f.severity,
    kind: f.kind,
    confidence: f.confidence,
    category: f.category,
    file: f.location.file,
    line: f.location.start_line ?? null,
    evidence_ids: f.evidence_ids,
    corroborated_by: f.corroborated_by,
  };
}

function stage(report: Report, name: string) {
  return report.pipeline.find((s) => s.name === name);
}

function num(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

export function recordedRun(report: Report = sampleReport): RecordedRun {
  return {
    analysisId: report.analysis_id,
    engine: report.engine_version,
    ruleset: report.ruleset_version,
    stages: stagesFromResults(report.pipeline),
    totalMs: report.pipeline.reduce((sum, s) => sum + s.duration_ms, 0),
    findings: report.findings.length,
    findingIds: report.findings.filter((f) => f.kind !== "ai").map((f) => f.id),
    priority: report.summary.review_priority.level,
    bySeverity: report.summary.by_severity,
  };
}

export interface InputsFigure {
  baseFiles: string[];
  changed: { path: string; status: FileSummary["status"]; additions: number; deletions: number }[];
  patchSha: string;
  snapshotFiles: number;
  snapshotBytes: number;
  repositoryFiles: number;
  coverageFormat: string | null;
  coverageFilename: string | null;
  additions: number;
  deletions: number;
}

export interface CallersFigure {
  symbols: {
    qualname: string;
    file: string;
    line: number | null;
    before: string | null;
    after: string | null;
    breaking: boolean;
    callSites: number;
    callSiteFiles: number;
    incompatible: number;
  }[];
  incompatible: Evidence[];
  checked: number;
  incompatibleTotal: number;
  findingId: string | null;
}

export interface LintFigure {
  diagnostics: { evidenceId: string; code: string; message: string; line: number | null; file: string; url: string | null }[];
  findings: SlimFinding[];
  tool: string;
  pythonFiles: number;
}

export interface RulesFigure {
  families: { group: string; label: string; count: number }[];
  logic: SlimFinding | null;
  logicEvidence: Evidence | null;
  /** The engine's own suggested check for the logic finding. */
  suggestion: string | null;
}

export interface CoverageFigure {
  symbols: { qualname: string; file: string; change: string; tests: number }[];
  files: { path: string; executable: number; covered: number; uncovered: number[] }[];
  covered: number;
  executable: number;
  percent: number | null;
  matchedFiles: number;
  unmatchedReportFiles: number;
  staleFiles: string[];
  format: string | null;
}

export interface AIFigure {
  provider: string | null;
  model: string | null;
  promptId: string | null;
  promptVersion: string | null;
  promptSha: string | null;
  requestSha: string | null;
  contextChars: number;
  truncated: boolean;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number | null;
  claims: number;
  accepted: number;
  rejected: number;
  note: { findingId: string; ruleId: string; findingTitle: string; explanation: string; evidenceIds: string[]; confidence: string } | null;
  assessment: string | null;
  /** Set only when the recorded free-text assessment misattributes the condition change (checked against the report). */
  assessmentIssue: { claimed: string; actual: string } | null;
}

export interface MatrixFigure {
  findings: SlimFinding[];
  priority: Report["summary"]["review_priority"];
}

// Labels describe what each counter in the rules stage summary measures (see backend analysis/*.py).
// A null key sums the whole group (AST pattern rules report one counter per rule that matched).
const RULE_FAMILIES: { group: string; key: string | null; label: string }[] = [
  { group: "textual", key: "secrets", label: "Secrets and credentials" },
  { group: "textual", key: "prompt_injection", label: "Prompt-injection text" },
  { group: "textual", key: "migrations", label: "Destructive migrations" },
  { group: "textual", key: "env_files", label: "Committed env files" },
  { group: "patterns", key: null, label: "Risky call patterns" },
  { group: "dependencies", key: "changes", label: "Dependency changes" },
  { group: "logic", key: "logic_changes", label: "Condition and operator flips" },
  { group: "metrics", key: "complexity", label: "Complexity past threshold" },
  { group: "metrics", key: "error_handling", label: "Removed error handling" },
  { group: "metrics", key: "assertions", label: "Removed assertions" },
  { group: "metrics", key: "deleted_tests", label: "Deleted tests" },
];

export function experienceData() {
  const r = sampleReport;
  const ai = sampleReportAI;
  const evidence = new Map(r.evidence.map((e) => [e.id, e]));
  const ingest = stage(r, "ingest")?.summary ?? {};
  const workspace = stage(r, "workspace")?.summary ?? {};
  const references = stage(r, "references")?.summary ?? {};
  const statics = stage(r, "static")?.summary ?? {};
  const rulesStage = (stage(r, "rules")?.summary ?? {}) as Record<string, Record<string, unknown>>;
  const coverageStage = stage(r, "coverage")?.summary ?? {};

  const inputs: InputsFigure = {
    baseFiles: sampleMeta.base_files,
    changed: r.files.map((f) => ({ path: f.path, status: f.status, additions: f.additions, deletions: f.deletions })),
    patchSha: r.input.patch_sha256,
    snapshotFiles: num(r.input.snapshot?.files ?? ingest.snapshot_files),
    snapshotBytes: num(r.input.snapshot?.bytes),
    repositoryFiles: num(workspace.repository_files),
    coverageFormat: r.input.coverage_format ?? null,
    coverageFilename: sampleMeta.coverage_filename,
    additions: r.summary.additions,
    deletions: r.summary.deletions,
  };

  const signatureChanged = (s: SymbolChangeSummary) => s.signature_before !== s.signature_after && s.change === "modified";
  const breaking = r.findings.find((f) => f.rule_id === "CG-API-001");
  const callers: CallersFigure = {
    symbols: r.symbols.filter(signatureChanged).map((s) => ({
      qualname: s.qualname,
      file: s.file,
      line: s.start_line ?? null,
      before: s.signature_before ?? null,
      after: s.signature_after ?? null,
      breaking: s.breaking,
      callSites: s.call_sites,
      callSiteFiles: s.call_site_files,
      incompatible: s.incompatible_call_sites,
    })),
    incompatible: r.evidence.filter((e) => e.type === "call_site"),
    checked: num(references.call_sites_checked),
    incompatibleTotal: num(references.incompatible),
    findingId: breaking?.id ?? null,
  };

  const diagnostics = r.evidence.filter((e) => e.type === "static_diagnostic");
  const lint: LintFigure = {
    diagnostics: diagnostics.map((e) => ({
      evidenceId: e.id,
      code: String(e.data.code ?? ""),
      message: String(e.data.message ?? e.title),
      line: e.start_line ?? null,
      file: e.file ?? "",
      url: typeof e.data.url === "string" ? e.data.url : null,
    })),
    findings: r.findings.filter((f) => f.evidence_ids.some((id) => evidence.get(id)?.type === "static_diagnostic")).map(slim),
    tool: String(statics.tool ?? "ruff"),
    pythonFiles: num(statics.python_files),
  };

  const logic = r.findings.find((f) => f.rule_id === "CG-LOG-001");
  const rules: RulesFigure = {
    families: RULE_FAMILIES.map((f) => ({
      group: f.group,
      label: f.label,
      count: f.key ? num(rulesStage[f.group]?.[f.key]) : Object.values(rulesStage[f.group] ?? {}).reduce<number>((sum, v) => sum + num(v), 0),
    })),
    logic: logic ? slim(logic) : null,
    logicEvidence: logic ? (evidence.get(logic.evidence_ids[0]) ?? null) : null,
    suggestion: logic?.suggested_test.description ?? null,
  };

  const coverage: CoverageFigure = {
    symbols: r.symbols
      .filter((s) => s.kind !== "test")
      .map((s) => ({ qualname: s.qualname, file: s.file, change: s.change, tests: s.related_tests })),
    files: r.files
      .filter((f) => f.coverage)
      .map((f) => ({
        path: f.path,
        executable: f.coverage?.executable ?? 0,
        covered: f.coverage?.covered ?? 0,
        uncovered: f.coverage?.uncovered_lines ?? [],
      })),
    covered: r.summary.patch_coverage?.covered ?? 0,
    executable: r.summary.patch_coverage?.executable ?? 0,
    percent: r.summary.patch_coverage?.percent ?? null,
    matchedFiles: num(coverageStage.matched_files),
    unmatchedReportFiles: num(coverageStage.unmatched_report_files),
    staleFiles: Array.isArray(coverageStage.stale_files) ? coverageStage.stale_files.map(String) : [],
    format: r.input.coverage_format ?? null,
  };

  const call = ai.ai.calls[0];
  const noted = ai.findings.find((f) => f.ai_analysis && f.kind !== "ai");
  const assessment = ai.ai.overall_assessment ?? null;
  // The recorded model summary names a function for the condition change. Check it against the report.
  const logicSymbol = logic?.related_symbols[0];
  const claimedMatch = assessment?.match(/condition logic in `([A-Za-z_][\w.]*)`/);
  const assessmentIssue =
    claimedMatch && logicSymbol && claimedMatch[1] !== logicSymbol ? { claimed: claimedMatch[1], actual: logicSymbol } : null;
  const aiFigure: AIFigure = {
    provider: ai.ai.provider ?? null,
    model: ai.ai.model ?? null,
    promptId: ai.ai.prompt_id ?? null,
    promptVersion: ai.ai.prompt_version ?? null,
    promptSha: ai.ai.prompt_sha256 ?? null,
    requestSha: call?.request_sha256 ?? null,
    contextChars: ai.ai.context_chars ?? 0,
    truncated: Boolean(ai.ai.context_truncated),
    inputTokens: call?.input_tokens ?? 0,
    outputTokens: call?.output_tokens ?? 0,
    latencyMs: call?.latency_ms ?? null,
    claims: ai.ai.verification?.claims_total ?? 0,
    accepted: ai.ai.verification?.claims_accepted ?? 0,
    rejected: ai.ai.verification?.claims_rejected ?? 0,
    note:
      noted && noted.ai_analysis
        ? {
            findingId: noted.id,
            ruleId: noted.rule_id,
            findingTitle: noted.title,
            explanation: noted.ai_analysis.explanation,
            evidenceIds: noted.ai_analysis.evidence_ids,
            confidence: noted.ai_analysis.confidence,
          }
        : null,
    assessment,
    assessmentIssue,
  };

  const matrix: MatrixFigure = { findings: r.findings.map(slim), priority: r.summary.review_priority };

  return {
    meta: sampleMeta,
    report: r,
    recorded: recordedRun(r),
    inputs,
    callers,
    lint,
    rules,
    coverage,
    ai: aiFigure,
    matrix,
    stageMs: Object.fromEntries(r.pipeline.map((s) => [s.name, s.duration_ms])) as Record<string, number>,
    aiStageMs: Object.fromEntries(ai.pipeline.map((s) => [s.name, s.duration_ms])) as Record<string, number>,
  };
}

export type ExperienceData = ReturnType<typeof experienceData>;
