import type { Category, Confidence, Provenance, Severity } from "./api/types";

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];
export const CONFIDENCE_ORDER: Confidence[] = ["high", "medium", "low"];
export const PROVENANCE_ORDER: Provenance[] = ["deterministic", "heuristic", "ai"];

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
};

export const PROVENANCE_META: Record<Provenance, { label: string; glyph: string; short: string; description: string }> = {
  deterministic: {
    label: "Deterministic",
    short: "Fact",
    glyph: "◆",
    description: "Established by analysis of your inputs: a parse, a resolved call, a measured line.",
  },
  heuristic: {
    label: "Heuristic",
    short: "Inference",
    glyph: "◇",
    description: "Inferred by a rule. Worth a reviewer's attention; impact depends on context.",
  },
  ai: {
    label: "AI-generated",
    short: "Proposal",
    glyph: "✦",
    description: "Proposed by a language model and verified to cite evidence ChangeGuard produced.",
  },
};

export const CATEGORY_LABEL: Record<Category, string> = {
  breaking_change: "Breaking change",
  behavior_change: "Behaviour change",
  logic_change: "Logic change",
  correctness: "Correctness",
  syntax_error: "Syntax error",
  security: "Security",
  secret_exposure: "Secret exposure",
  error_handling: "Error handling",
  concurrency: "Concurrency",
  test_gap: "Test gap",
  coverage_gap: "Coverage gap",
  test_integrity: "Test integrity",
  data_migration: "Data migration",
  dependency: "Dependency",
  complexity: "Complexity",
  debug_artifact: "Debug artifact",
  configuration: "Configuration",
  type_safety: "Type safety",
  prompt_injection: "Prompt injection",
};

export const PRIORITY_META: Record<string, { label: string; tone: "danger" | "signal" | "medium" | "quiet"; blurb: string }> = {
  block: { label: "Block", tone: "danger", blurb: "Critical issues established by deterministic analysis." },
  high: { label: "High", tone: "signal", blurb: "High-severity findings need a reviewer's eyes." },
  elevated: { label: "Elevated", tone: "medium", blurb: "Medium-severity findings worth checking." },
  routine: { label: "Routine", tone: "quiet", blurb: "Only low-severity or informational findings." },
};

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1) return `${ms.toFixed(2)} ms`;
  if (ms < 10) return `${ms.toFixed(1)} ms`;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatRelative(iso: string, now: Date): string {
  const then = new Date(iso);
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);
  if (Number.isNaN(seconds)) return iso;
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return then.toISOString().slice(0, 10);
}

export function formatLocation(file: string, start?: number | null, end?: number | null): string {
  if (!start) return file;
  return end && end !== start ? `${file}:${start}–${end}` : `${file}:${start}`;
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function languageForPath(path: string | null | undefined): string {
  if (!path) return "text";
  const ext = path.slice(path.lastIndexOf(".") + 1).toLowerCase();
  return (
    {
      py: "python",
      pyi: "python",
      ts: "typescript",
      mts: "typescript",
      cts: "typescript",
      tsx: "tsx",
      js: "javascript",
      mjs: "javascript",
      cjs: "javascript",
      jsx: "jsx",
      sql: "sql",
      json: "json",
      toml: "toml",
      yml: "yaml",
      yaml: "yaml",
      sh: "bash",
      md: "markdown",
    } as Record<string, string>
  )[ext] ?? "text";
}
