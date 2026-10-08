"use client";

import { useMemo } from "react";

import type { FileSummary, Finding, Report } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDuration, formatPercent, SEVERITY_ORDER } from "@/lib/format";
import { stagesFromResults } from "@/lib/stages";

import { DiffViewer } from "../code/diff-viewer";
import { Pill, SeverityMark } from "../ui/badges";
import { Notice } from "../ui/primitives";
import { PipelineTrack } from "../viz/pipeline-track";
import { renderInlineCode } from "./evidence";

const STATUS_GLYPH: Record<FileSummary["status"], { label: string; className: string }> = {
  added: { label: "A", className: "text-ok border-ok/40" },
  deleted: { label: "D", className: "text-danger border-danger/40" },
  modified: { label: "M", className: "text-signal border-signal/40" },
  renamed: { label: "R", className: "text-ai border-ai/40" },
  copied: { label: "C", className: "text-ai border-ai/40" },
};

export function ChangesPanel({
  report,
  activeFile,
  onActiveFile,
  focusLine,
  onSelectFinding,
}: {
  report: Report;
  activeFile: string;
  onActiveFile: (path: string) => void;
  focusLine?: number | null;
  onSelectFinding: (id: string) => void;
}) {
  const file = report.files.find((f) => f.path === activeFile) ?? report.files[0];
  const findingsByFile = useMemo(() => {
    const map = new Map<string, Finding[]>();
    for (const f of report.findings) map.set(f.location.file, [...(map.get(f.location.file) ?? []), f]);
    return map;
  }, [report.findings]);

  return (
    <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
      <nav aria-label="Changed files" className="min-w-0">
        <ul className="space-y-0.5">
          {report.files.map((f) => {
            const findings = findingsByFile.get(f.path) ?? [];
            const worst = SEVERITY_ORDER.find((s) => findings.some((x) => x.severity === s));
            const active = f.path === file?.path;
            return (
              <li key={f.path}>
                <button
                  type="button"
                  onClick={() => onActiveFile(f.path)}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-[0.8125rem] transition-colors",
                    active ? "bg-surface-2 text-ink" : "text-ink-soft hover:bg-surface",
                  )}
                >
                  <span
                    className={cn("flex size-4 shrink-0 items-center justify-center rounded-[3px] border font-mono text-[0.5625rem] font-bold", STATUS_GLYPH[f.status].className)}
                    title={f.status}
                  >
                    {STATUS_GLYPH[f.status].label}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-mono text-[0.75rem]" title={f.path}>
                    {f.path}
                  </span>
                  {worst && <SeverityMark severity={worst} />}
                  <span className="numeric shrink-0 font-mono text-[0.625rem]">
                    <span className="text-ok">+{f.additions}</span> <span className="text-danger">−{f.deletions}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      {file && (
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="font-mono text-[0.8125rem] text-ink">{file.path}</span>
            {file.old_path && <span>(was {file.old_path})</span>}
            <Pill className="h-5 text-[0.6875rem]">{file.language}</Pill>
            {!file.structural_support && <Pill className="h-5 text-[0.6875rem]">line-level rules only</Pill>}
            {!file.full_context && !file.is_binary && <Pill tone="signal" className="h-5 text-[0.6875rem]">diff hunks only</Pill>}
            {file.coverage && (
              <Pill tone={file.coverage.covered === file.coverage.executable ? "ok" : "signal"} className="h-5 text-[0.6875rem] numeric">
                {file.coverage.covered}/{file.coverage.executable} changed lines covered
              </Pill>
            )}
          </div>
          <DiffViewer
            file={file}
            findings={report.findings}
            highlightLines={focusLine ? [focusLine] : []}
            onSelect={onSelectFinding}
            maxHeight={720}
          />
          <p className="text-xs text-muted">Markers in the gutter are findings; select one to open it. Secrets are masked in this view.</p>
        </div>
      )}
    </div>
  );
}

export function SymbolsPanel({ report }: { report: Report }) {
  const rows = report.symbols.filter((s) => s.kind !== "test");
  if (!rows.length) return <Notice title="No structural changes">No functions, methods, or classes changed in files with structural support.</Notice>;
  return (
    <div className="relative overflow-x-auto rounded-[10px] border border-line scrollbar-thin">
      <table className="w-full min-w-[760px] border-collapse text-[0.8125rem]">
        <thead>
          <tr className="border-b border-line bg-surface text-left text-xs text-muted">
            <th className="px-3 py-2.5 font-medium">Symbol</th>
            <th className="px-3 py-2.5 font-medium">Change</th>
            <th className="px-3 py-2.5 font-medium">Signature</th>
            <th className="px-3 py-2.5 text-right font-medium">Callers</th>
            <th className="px-3 py-2.5 text-right font-medium">Tests</th>
            <th className="px-3 py-2.5 text-right font-medium">Complexity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={`${s.file}:${s.qualname}`} className="border-b border-line last:border-b-0 align-top">
              <td className="px-3 py-2.5">
                <div className="font-mono text-[0.75rem] font-medium text-ink">{s.qualname}</div>
                <div className="mt-0.5 font-mono text-[0.6875rem] text-faint">
                  {s.file}
                  {s.start_line ? `:${s.start_line}` : ""}
                </div>
              </td>
              <td className="px-3 py-2.5">
                <span className="capitalize text-ink-soft">{s.change}</span>
                {s.renamed_from && <div className="text-xs text-muted">from {s.renamed_from}</div>}
                {s.breaking && <Pill tone="danger" className="mt-1 h-5 text-[0.6875rem]">breaking</Pill>}
                {s.approximate && <div className="mt-1 text-[0.6875rem] text-faint">from diff hunks</div>}
              </td>
              <td className="max-w-[340px] px-3 py-2.5 font-mono text-[0.6875rem] leading-relaxed">
                {s.signature_before && s.signature_before !== s.signature_after && (
                  <div className="text-danger line-through decoration-danger/40">{s.signature_before}</div>
                )}
                {s.signature_after && <div className="text-ink-soft">{s.signature_after}</div>}
              </td>
              <td className="px-3 py-2.5 text-right numeric">
                {s.call_sites}
                {s.incompatible_call_sites > 0 && <div className="text-xs text-danger">{s.incompatible_call_sites} incompatible</div>}
              </td>
              <td className={cn("px-3 py-2.5 text-right numeric", s.related_tests === 0 && s.change !== "removed" ? "text-signal" : "text-ink-soft")}>
                {s.change === "removed" ? "—" : s.related_tests}
              </td>
              <td className="px-3 py-2.5 text-right numeric text-ink-soft">
                {s.complexity_after ?? "—"}
                {s.complexity_before != null && s.complexity_after != null && s.complexity_after !== s.complexity_before && (
                  <span className={cn("ml-1 text-xs", s.complexity_after > s.complexity_before ? "text-signal" : "text-ok")}>
                    ({s.complexity_after > s.complexity_before ? "+" : ""}
                    {s.complexity_after - s.complexity_before})
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PipelinePanel({ report }: { report: Report }) {
  const stages = stagesFromResults(report.pipeline);
  const total = report.pipeline.reduce((sum, s) => sum + s.duration_ms, 0);
  const max = Math.max(...report.pipeline.map((s) => s.duration_ms), 1);
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        <h3 className="mb-3 text-sm font-semibold">Stages</h3>
        <PipelineTrack stages={stages} />
      </div>
      <div>
        <h3 className="mb-3 text-sm font-semibold">
          Time per stage <span className="font-normal text-muted">· {formatDuration(total)} total</span>
        </h3>
        <ul className="space-y-2.5">
          {report.pipeline.map((s) => (
            <li key={s.name} className="grid grid-cols-[120px_1fr_64px] items-center gap-3 text-xs">
              <span className="truncate text-ink-soft">{s.label}</span>
              <span className="h-2 overflow-hidden rounded-full bg-surface-2">
                <span
                  className={cn("block h-full rounded-full", s.status === "failed" ? "bg-danger" : s.status === "skipped" ? "bg-line-strong" : "bg-ink")}
                  style={{ width: `${Math.max(1.5, (s.duration_ms / max) * 100)}%` }}
                />
              </span>
              <span className="text-right font-mono text-muted numeric">{s.status === "skipped" ? "skipped" : formatDuration(s.duration_ms)}</span>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs leading-relaxed text-muted">
          Stage timings are measured inside the engine for this run. Model latency appears under Synthesis when AI is enabled.
        </p>
      </div>
    </div>
  );
}

export function AIPanel({ report }: { report: Report }) {
  const ai = report.ai;
  if (ai.status === "disabled" || (ai.status === "skipped" && !ai.calls.length)) {
    return (
      <div className="max-w-2xl space-y-4">
        <Notice title={ai.status === "skipped" ? "AI was requested but no provider is configured" : "AI synthesis was off for this analysis"}>
          {ai.note} Explanations come from rule templates, so every word in this report traces to a deterministic rule.
        </Notice>
        <p className="prose-lab text-sm">
          To enable it, run a local model with Ollama (<code>CHANGEGUARD_AI_PROVIDER=ollama</code>) or point the engine at any
          OpenAI-compatible server or the Claude API. Model output is verified against the evidence before it reaches a report.
        </p>
      </div>
    );
  }
  const v = ai.verification;
  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Status" value={ai.status === "completed" ? "Completed" : "Failed"} tone={ai.status === "completed" ? "ok" : "danger"} />
        <Stat label="Model" value={ai.model ?? "—"} mono sub={ai.provider ?? undefined} />
        <Stat
          label="Claims verified"
          value={v ? `${v.claims_accepted} / ${v.claims_total}` : "—"}
          sub={v && v.claims_rejected ? `${v.claims_rejected} rejected` : "none rejected"}
        />
        <Stat
          label="Prompt"
          value={`${ai.prompt_id ?? "—"} v${ai.prompt_version ?? "?"}`}
          mono
          sub={ai.prompt_sha256 ? `sha256 ${ai.prompt_sha256.slice(0, 12)}…` : undefined}
        />
      </div>

      {ai.note && <Notice tone={ai.status === "failed" ? "danger" : "neutral"}>{ai.note}</Notice>}

      <section>
        <h3 className="mb-3 text-sm font-semibold">Model calls</h3>
        <div className="relative overflow-x-auto rounded-[10px] border border-line scrollbar-thin">
          <table className="w-full min-w-[640px] text-[0.8125rem]">
            <thead>
              <tr className="border-b border-line bg-surface text-left text-xs text-muted">
                <th className="px-3 py-2 font-medium">Call</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Latency</th>
                <th className="px-3 py-2 text-right font-medium">Tokens in / out</th>
                <th className="px-3 py-2 font-medium">Cache</th>
              </tr>
            </thead>
            <tbody>
              {ai.calls.map((call) => (
                <tr key={call.call_id} className="border-b border-line last:border-0">
                  <td className="px-3 py-2 font-mono text-[0.6875rem] text-muted">
                    {call.call_id} · attempt {call.attempts}
                  </td>
                  <td className="px-3 py-2">
                    <Pill tone={call.status === "ok" ? "ok" : "danger"} className="h-5 text-[0.6875rem]">
                      {call.status.replace("_", " ")}
                    </Pill>
                    {call.error && <div className="mt-1 max-w-xs text-xs text-muted">{call.error}</div>}
                  </td>
                  <td className="px-3 py-2 text-right font-mono numeric">{formatDuration(call.latency_ms)}</td>
                  <td className="px-3 py-2 text-right font-mono numeric">
                    {call.input_tokens ?? "—"} / {call.output_tokens ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted">{call.cache_hit ? "hit" : "miss"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          Context sent to the model: {ai.context_chars?.toLocaleString() ?? "—"} characters
          {ai.context_truncated ? " (truncated to the highest-severity findings)" : ""}. Secrets and prompt-injection text are
          withheld from it.
        </p>
      </section>

      {v && v.rejected.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-semibold">Rejected claims</h3>
          <p className="mb-3 text-xs text-muted">Model statements that failed grounding verification. They do not appear anywhere else in the report.</p>
          <ul className="space-y-2">
            {v.rejected.map((claim, i) => (
              <li key={i} className="rounded-[10px] border border-line p-3">
                <p className="text-[0.8125rem] text-ink-soft">
                  <span className="mr-2 font-mono text-[0.6875rem] text-faint">{claim.target}</span>
                  {claim.summary}
                </p>
                <ul className="mt-2 space-y-1">
                  {claim.reasons.map((reason) => (
                    <li key={reason} className="flex gap-2 text-xs text-danger">
                      <span aria-hidden="true">×</span>
                      <span>{renderInlineCode(reason)}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="text-xs leading-relaxed text-muted">
        The model is also asked for a short free-text summary. Free text cannot be verified claim by claim, so it is kept in the
        JSON trace for research and never shown as part of the report.
      </p>
    </div>
  );
}

function Stat({ label, value, sub, mono, tone }: { label: string; value: string; sub?: string; mono?: boolean; tone?: "ok" | "danger" }) {
  return (
    <div className="rounded-[10px] border border-line p-3.5">
      <div className="text-xs text-muted">{label}</div>
      <div className={cn("mt-1 truncate text-[0.9375rem] font-semibold", mono && "font-mono text-[0.8125rem]", tone === "ok" && "text-ok", tone === "danger" && "text-danger")}>
        {value}
      </div>
      {sub && <div className="mt-0.5 truncate font-mono text-[0.6875rem] text-faint">{sub}</div>}
    </div>
  );
}

export function LimitationsPanel({ report }: { report: Report }) {
  const input = report.input;
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <div className="space-y-6">
        {report.warnings.length > 0 && (
          <section>
            <h3 className="mb-3 text-sm font-semibold">Warnings for this run</h3>
            <ul className="space-y-2">
              {report.warnings.map((w) => (
                <li key={w}>
                  <Notice tone="signal">{w}</Notice>
                </li>
              ))}
            </ul>
          </section>
        )}
        <section>
          <h3 className="mb-3 text-sm font-semibold">What this analysis cannot tell you</h3>
          <ul className="space-y-3">
            {report.limitations.map((l) => (
              <li key={l} className="flex gap-3 text-[0.875rem] leading-relaxed text-ink-soft">
                <span className="mt-[0.6em] size-1.5 shrink-0 rounded-full bg-faint" aria-hidden="true" />
                {l}
              </li>
            ))}
          </ul>
        </section>
      </div>
      <section className="rounded-[10px] border border-line p-4">
        <h3 className="mb-3 text-sm font-semibold">Inputs</h3>
        <dl className="space-y-2.5 text-[0.8125rem]">
          <Row label="Mode" value={input.mode === "full_context" ? "Full context (repository snapshot)" : "Diff only"} />
          <Row label="Patch format" value={input.patch_format} />
          <Row label="Patch SHA-256" value={`${input.patch_sha256.slice(0, 20)}…`} mono />
          <Row
            label="Snapshot"
            value={
              input.snapshot
                ? `${input.snapshot.files as number} files${input.snapshot.root_prefix ? ` (root ${String(input.snapshot.root_prefix)}/ stripped)` : ""}`
                : "none"
            }
          />
          <Row label="Coverage" value={input.coverage_format ?? "none"} />
          <Row label="Engine" value={`${report.engine_version} · ruleset ${report.ruleset_version}`} mono />
          <Row label="Report schema" value={report.schema_version} mono />
          {report.summary.patch_coverage && (
            <Row
              label="Patch coverage"
              value={`${formatPercent(report.summary.patch_coverage.percent != null ? report.summary.patch_coverage.percent / 100 : null)} of ${report.summary.patch_coverage.executable} lines`}
            />
          )}
        </dl>
      </section>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted">{label}</dt>
      <dd className={cn("text-right text-ink", mono && "font-mono text-[0.75rem]")}>{value}</dd>
    </div>
  );
}
