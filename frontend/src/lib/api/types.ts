// Types generated from the backend's OpenAPI document (`npm run gen:api`).
import type { components } from "./schema";

type S = components["schemas"];

export type Report = S["Report"];
export type Finding = S["Finding"];
export type Evidence = S["Evidence"];
export type FileSummary = S["FileSummary"];
export type HunkModel = S["HunkModel"];
export type HunkLine = S["HunkLine"];
export type SymbolChangeSummary = S["SymbolChangeSummary"];
export type StageResult = S["StageResult"];
export type AISummary = S["AISummary"];
export type ModelCallTrace = S["ModelCallTrace"];
export type AIAnalysis = S["AIAnalysis"];
export type SuggestedTest = S["SuggestedTest"];
export type Summary = S["Summary"];
export type ReviewPriority = S["ReviewPriority"];
export type AnalysisSummary = S["AnalysisSummary"];
export type AnalysisDetail = S["AnalysisDetail"];
export type AnalysisList = S["AnalysisList"];
export type HistorySummary = S["HistorySummary"];
export type SampleSummary = S["SampleSummary"];
export type SampleDetail = S["SampleDetail"];
export type Meta = S["Meta"];
export type RuleInfo = S["RuleInfo"];
export type Problem = S["Problem"];

export type Severity = Finding["severity"];
export type Confidence = Finding["confidence"];
export type Provenance = Finding["kind"];
export type Category = Finding["category"];
export type EvidenceType = Evidence["type"];

/** Server-sent progress events emitted while an analysis runs. */
export type StageEvent =
  | { type: "started"; analysis_id: string }
  | { type: "stage"; status: "running"; name: string; label: string }
  | ({ type: "stage" } & StageResult)
  | { type: "completed"; analysis_id: string; duration_ms: number; summary: HistorySummary }
  | { type: "failed"; error: { code: string; message: string } };
