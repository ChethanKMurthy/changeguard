"use client";

import { DropdownMenu } from "radix-ui";
import Link from "next/link";
import { useCallback, useMemo, useState, useSyncExternalStore } from "react";

import { api } from "@/lib/api/client";
import type { AnalysisDetail, Finding, Report } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDuration, PRIORITY_META, PROVENANCE_META, PROVENANCE_ORDER, SEVERITY_LABEL, SEVERITY_ORDER } from "@/lib/format";

import { Pill, SeverityMark } from "../ui/badges";
import { RelativeTime } from "../ui/relative-time";
import { Notice, Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/primitives";
import { FindingsPanel } from "./findings-panel";
import { AIPanel, ChangesPanel, LimitationsPanel, PipelinePanel, SymbolsPanel } from "./report-panels";

export interface ExportLinks {
  json: string;
  markdown: string;
  sarif: string;
}

function ExportMenu({ links }: { links: ExportLinks }) {
  const items: { format: "markdown" | "sarif" | "json"; label: string; hint: string }[] = [
    { format: "markdown", label: "Markdown", hint: "Paste into a pull request" },
    { format: "sarif", label: "SARIF 2.1.0", hint: "GitHub code scanning" },
    { format: "json", label: "JSON", hint: "Full report, schema 1.0" },
  ];
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="inline-flex h-9 items-center gap-2 rounded-md border border-line-strong bg-bg px-3 text-sm font-medium text-ink transition-colors hover:bg-surface data-[state=open]:bg-surface">
        Export
        <svg viewBox="0 0 12 12" className="size-3" aria-hidden="true">
          <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className="z-20 min-w-[230px] rounded-[10px] border border-line bg-raised p-1.5 shadow-float">
          {items.map((item) => (
            <DropdownMenu.Item key={item.format} asChild>
              <a
                href={links[item.format]}
                download
                className="flex cursor-pointer flex-col rounded-md px-2.5 py-2 outline-none data-[highlighted]:bg-surface-2"
              >
                <span className="text-sm font-medium text-ink">{item.label}</span>
                <span className="text-xs text-muted">{item.hint}</span>
              </a>
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function PriorityPanel({ report }: { report: Report }) {
  const p = report.summary.review_priority;
  const meta = PRIORITY_META[p.level];
  const tone = {
    danger: "border-danger/40 bg-danger-tint",
    signal: "border-signal/40 bg-signal-tint",
    medium: "border-sev-medium/50 bg-signal-tint/60",
    quiet: "border-line bg-surface",
  }[meta.tone];
  const ink = { danger: "text-danger", signal: "text-signal", medium: "text-sev-medium-ink", quiet: "text-ink" }[meta.tone];
  return (
    <div className={cn("self-start rounded-[12px] border p-4", tone)}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs font-medium text-muted">Review priority</span>
        <span className="font-mono text-[0.6875rem] text-muted">rule-based label</span>
      </div>
      <div className={cn("mt-1 text-2xl font-[650] tracking-[-0.02em] [font-stretch:115%]", ink)}>{meta.label}</div>
      <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-ink-soft">{p.rationale}</p>
      <p className="mt-2 text-[0.6875rem] leading-relaxed text-muted">
        A triage label computed from severity and provenance, not a probability of failure.
      </p>
    </div>
  );
}

function SeverityBar({ report }: { report: Report }) {
  const counts = report.summary.by_severity;
  const total = report.summary.findings_total || 1;
  const colors: Record<string, string> = {
    critical: "bg-sev-critical",
    high: "bg-sev-high",
    medium: "bg-sev-medium",
    low: "bg-sev-low",
    info: "bg-sev-info",
  };
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
        {SEVERITY_ORDER.map((s) =>
          counts[s] ? <span key={s} className={colors[s]} style={{ width: `${(counts[s] / total) * 100}%` }} /> : null,
        )}
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted">
        {SEVERITY_ORDER.map((s) =>
          counts[s] ? (
            <li key={s} className="flex items-center gap-1.5">
              <SeverityMark severity={s} />
              <span className="numeric font-semibold text-ink">{counts[s]}</span> {SEVERITY_LABEL[s].toLowerCase()}
            </li>
          ) : null,
        )}
      </ul>
    </div>
  );
}

function subscribeHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function readHash() {
  return window.location.hash.slice(1);
}

export function ReportView({
  analysis,
  report,
  exports,
  banner,
}: {
  analysis?: AnalysisDetail;
  report: Report;
  /** Export downloads; defaults to the engine's export endpoints for this analysis. */
  exports?: ExportLinks;
  /** Context shown above the report (e.g. that it is a recorded run). */
  banner?: React.ReactNode;
}) {
  const exportLinks = exports ?? {
    json: api.exportUrl(report.analysis_id, "json"),
    markdown: api.exportUrl(report.analysis_id, "markdown"),
    sarif: api.exportUrl(report.analysis_id, "sarif"),
  };
  const evidence = useMemo(() => new Map(report.evidence.map((e) => [e.id, e])), [report.evidence]);
  const [tab, setTab] = useState("findings");
  const hash = useSyncExternalStore(subscribeHash, readHash, () => "");
  const [picked, setPicked] = useState<string | null>(null);
  const selectedId = picked ?? (report.findings.some((f) => f.id === hash) ? hash : null);
  const [activeFile, setActiveFile] = useState(report.files[0]?.path ?? "");
  const [focusLine, setFocusLine] = useState<number | null>(null);

  const select = useCallback((id: string) => {
    setPicked(id);
    window.history.replaceState(null, "", `#${id}`);
  }, []);

  const showInDiff = useCallback(
    (finding: Finding) => {
      if (!report.files.some((f) => f.path === finding.location.file)) return;
      setActiveFile(finding.location.file);
      setFocusLine(finding.location.side === "head" ? finding.location.start_line ?? null : null);
      setTab("changes");
      requestAnimationFrame(() => {
        if (finding.location.start_line && finding.location.side === "head") {
          document.getElementById(`L${finding.location.start_line}`)?.scrollIntoView({ block: "center" });
        }
      });
    },
    [report.files],
  );

  const s = report.summary;
  const kinds = s.by_kind;
  return (
    <div className="mx-auto max-w-[1240px] px-4 pb-10 pt-8 sm:px-6">
      <nav aria-label="Breadcrumb" className="text-xs text-muted">
        <Link href="/history" className="hover:text-ink">
          Reports
        </Link>
        <span className="mx-1.5 text-faint">/</span>
        <span className="font-mono">{report.analysis_id}</span>
      </nav>
      {banner}

      <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:gap-10">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={report.input.mode === "full_context" ? "neutral" : "signal"}>
              {report.input.mode === "full_context" ? "Full context" : "Diff only"}
            </Pill>
            {(analysis?.sample_id || report.analysis_id.startsWith("sample-")) && <Pill tone="signal">Synthetic sample data</Pill>}
            {report.input.has_coverage && <Pill>Coverage · {report.input.coverage_format}</Pill>}
            <Pill tone={report.ai.status === "completed" ? "ai" : "neutral"}>
              {report.ai.status === "completed" ? `✦ AI · ${report.ai.model}` : "AI off"}
            </Pill>
          </div>
          <h1 className="mt-4 text-[clamp(1.6rem,3vw,2.35rem)] font-[640] leading-[1.12] tracking-[-0.025em] [font-stretch:110%]">
            {report.title}
          </h1>
          <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[0.8125rem] text-muted">
            <div>
              <dt className="sr-only">Changed</dt>
              <dd>
                <span className="numeric font-semibold text-ink">{s.files_changed}</span> files ·{" "}
                <span className="numeric text-ok">+{s.additions}</span> <span className="numeric text-danger">−{s.deletions}</span>
              </dd>
            </div>
            <div>
              <dt className="sr-only">Symbols</dt>
              <dd>
                <span className="numeric font-semibold text-ink">{s.changed_symbols}</span> symbols changed ·{" "}
                <span className="numeric font-semibold text-ink">{s.breaking_symbols}</span> breaking
              </dd>
            </div>
            {s.patch_coverage?.percent != null && (
              <div>
                <dt className="sr-only">Patch coverage</dt>
                <dd>
                  <span className="numeric font-semibold text-ink">{s.patch_coverage.percent}%</span> patch coverage
                </dd>
              </div>
            )}
            <div>
              <dt className="sr-only">Languages</dt>
              <dd>{s.languages.join(", ")}</dd>
            </div>
            <div>
              <dt className="sr-only">Analysed</dt>
              <dd>
                <RelativeTime iso={report.created_at} />
                {analysis?.duration_ms != null && ` in ${formatDuration(analysis.duration_ms)}`}
              </dd>
            </div>
          </dl>
          <div className="mt-6 grid gap-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <div className="min-w-0">
              <div className="mb-2 flex items-baseline gap-2">
                <span className="text-3xl font-[650] tracking-[-0.03em] numeric [font-stretch:112%]">{s.findings_total}</span>
                <span className="text-sm text-muted">findings</span>
                <span className="ml-3 flex flex-wrap gap-x-3 text-xs text-muted">
                  {PROVENANCE_ORDER.map((k) => (
                    <span key={k} className="whitespace-nowrap">
                      <span aria-hidden="true" className={k === "ai" ? "text-ai" : undefined}>
                        {PROVENANCE_META[k].glyph}
                      </span>{" "}
                      <span className="numeric font-medium text-ink">{kinds[k] ?? 0}</span> {PROVENANCE_META[k].label.toLowerCase()}
                    </span>
                  ))}
                </span>
              </div>
              <SeverityBar report={report} />
            </div>
            <div className="flex gap-2">
              <ExportMenu links={exportLinks} />
            </div>
          </div>
        </div>
        <PriorityPanel report={report} />
      </div>

      {report.warnings.length > 0 && (
        <Notice tone="signal" className="mt-6" title={`${report.warnings.length} warning${report.warnings.length > 1 ? "s" : ""} for this run`}>
          {report.warnings[0]}
          {report.warnings.length > 1 && " — see Limitations for the rest."}
        </Notice>
      )}

      <Tabs value={tab} onValueChange={setTab} className="mt-8">
        <TabsList>
          <TabsTrigger value="findings" count={report.findings.length}>
            Findings
          </TabsTrigger>
          <TabsTrigger value="changes" count={report.files.length}>
            Changes
          </TabsTrigger>
          <TabsTrigger value="symbols" count={report.symbols.filter((x) => x.kind !== "test").length}>
            Symbols
          </TabsTrigger>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="ai">{report.ai.status === "completed" ? "✦ AI trace" : "AI"}</TabsTrigger>
          <TabsTrigger value="limits">Limitations</TabsTrigger>
        </TabsList>
        <TabsContent value="findings" className="pt-6 outline-none">
          <FindingsPanel
            findings={report.findings}
            evidence={evidence}
            selectedId={selectedId}
            onSelect={select}
            onShowInDiff={showInDiff}
          />
        </TabsContent>
        <TabsContent value="changes" className="pt-6 outline-none">
          <ChangesPanel
            report={report}
            activeFile={activeFile}
            onActiveFile={(p) => {
              setActiveFile(p);
              setFocusLine(null);
            }}
            focusLine={focusLine}
            onSelectFinding={(id) => {
              select(id);
              setTab("findings");
            }}
          />
        </TabsContent>
        <TabsContent value="symbols" className="pt-6 outline-none">
          <SymbolsPanel report={report} />
        </TabsContent>
        <TabsContent value="pipeline" className="pt-6 outline-none">
          <PipelinePanel report={report} />
        </TabsContent>
        <TabsContent value="ai" className="pt-6 outline-none">
          <AIPanel report={report} />
        </TabsContent>
        <TabsContent value="limits" className="pt-6 outline-none">
          <LimitationsPanel report={report} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
