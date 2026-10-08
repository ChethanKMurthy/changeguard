"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Pill } from "@/components/ui/badges";
import { ButtonLink } from "@/components/ui/button";
import { Notice, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api/client";
import type { AnalysisSummary } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { RelativeTime } from "@/components/ui/relative-time";
import { formatDuration, PRIORITY_META, SEVERITY_ORDER } from "@/lib/format";
import { invalidate, useResource } from "@/lib/use-resource";

const SEV_BG: Record<string, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
  info: "bg-sev-info",
};

function SeverityMix({ counts, total }: { counts: Record<string, number>; total: number }) {
  if (!total) return <span className="text-xs text-faint">no findings</span>;
  return (
    <span className="flex h-1.5 w-28 overflow-hidden rounded-full bg-surface-2" title={SEVERITY_ORDER.map((s) => `${counts[s] ?? 0} ${s}`).join(" · ")}>
      {SEVERITY_ORDER.map((s) => (counts[s] ? <span key={s} className={SEV_BG[s]} style={{ width: `${(counts[s] / total) * 100}%` }} /> : null))}
    </span>
  );
}

function StatusCell({ item }: { item: AnalysisSummary }) {
  if (item.status === "completed" && item.summary) {
    const p = PRIORITY_META[item.summary.review_priority ?? "routine"];
    return (
      <span className={cn("text-sm font-semibold", p.tone === "danger" ? "text-danger" : p.tone === "signal" ? "text-signal" : p.tone === "medium" ? "text-sev-medium-ink" : "text-ink-soft")}>
        {p.label}
      </span>
    );
  }
  if (item.status === "failed") return <Pill tone="danger" className="h-5 text-[0.6875rem]">Failed</Pill>;
  return <Pill tone="signal" className="h-5 text-[0.6875rem]">{item.status === "running" ? "Running" : "Queued"}</Pill>;
}

export function HistoryList() {
  const reduce = useReducedMotion();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [removing, setRemoving] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);
  const list = useResource(`analyses:${debounced}`, () => api.analyses({ limit: 50, q: debounced || undefined }), { maxAgeMs: 0 });

  const remove = async (id: string) => {
    setRemoving(id);
    try {
      await api.deleteAnalysis(id);
      invalidate("analyses:");
      await list.reload();
    } finally {
      setRemoving(null);
    }
  };

  const items = list.data?.items ?? [];
  return (
    <div className="mx-auto max-w-[1240px] px-4 pb-16 pt-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="text-[clamp(2rem,4vw,3rem)] font-[640] leading-[1.05] tracking-[-0.03em] [font-stretch:115%]">Reports</h1>
          <p className="mt-3 max-w-xl text-[0.9375rem] leading-relaxed text-muted">
            Analyses run from this browser, newest first. On a shared deployment each browser sees only its own reports.
            They are stored in the engine&rsquo;s SQLite database; uploaded archives are never kept.
          </p>
        </div>
        <div className="flex w-full items-center gap-3 sm:w-auto">
          <label className="relative min-w-0 flex-1 sm:flex-none">
            <span className="sr-only">Search reports</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by title"
              className="h-10 w-full rounded-md border border-line bg-bg px-3 text-sm placeholder:text-muted focus:border-ink focus:outline-none sm:w-60"
            />
          </label>
          <ButtonLink href="/analyze">New analysis</ButtonLink>
        </div>
      </div>

      <div className="mt-8">
        {list.error && (
          <Notice tone="danger" title="Could not load reports">
            {list.error.message}
          </Notice>
        )}
        {list.loading && !list.data && (
          <div className="space-y-2" aria-busy="true">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        )}
        {list.data && items.length === 0 && (
          <div className="rounded-[12px] border border-dashed border-line-strong px-6 py-16 text-center">
            <p className="text-lg font-semibold">{debounced ? "No reports match" : "No reports yet"}</p>
            <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
              {debounced
                ? "Try a different title, or clear the search."
                : "Analyse a diff from your own repository, or start with one of the synthetic samples to see a full report."}
            </p>
            {!debounced && (
              <div className="mt-6 flex flex-wrap justify-center gap-3">
                <ButtonLink href="/analyze">Analyse a diff</ButtonLink>
                <ButtonLink href="/experience" variant="secondary">
                  Take the guided experience
                </ButtonLink>
              </div>
            )}
          </div>
        )}
        {items.length > 0 && (
          <div className="relative overflow-x-auto rounded-[12px] border border-line scrollbar-thin">
            <table className="w-full min-w-[820px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line bg-surface text-left text-xs text-muted">
                  <th className="px-4 py-2.5 font-medium">Change</th>
                  <th className="px-4 py-2.5 font-medium">Priority</th>
                  <th className="px-4 py-2.5 font-medium">Findings</th>
                  <th className="px-4 py-2.5 font-medium">Scope</th>
                  <th className="px-4 py-2.5 font-medium">When</th>
                  <th className="px-4 py-2.5">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence initial={false}>
                  {items.map((item) => {
                    const s = item.summary;
                    return (
                      <motion.tr
                        key={item.id}
                        layout={reduce ? false : "position"}
                        initial={reduce ? false : { opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="group border-b border-line last:border-0 hover:bg-surface/60"
                      >
                        <td className="max-w-[420px] px-4 py-3">
                          <Link href={`/reports/${item.id}`} className="font-medium text-ink hover:underline">
                            {item.title}
                          </Link>
                          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                            <span className="font-mono text-[0.6875rem] text-faint">{item.id}</span>
                            {item.sample_id && <span>· sample</span>}
                            {item.ai_requested && <span className="text-ai">· ✦ AI</span>}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <StatusCell item={item} />
                          {item.error && <div className="mt-0.5 max-w-[220px] truncate text-xs text-muted" title={item.error.message}>{item.error.message}</div>}
                        </td>
                        <td className="px-4 py-3">
                          {s ? (
                            <span className="flex items-center gap-3">
                              <span className="w-6 text-right font-semibold numeric">{s.findings_total}</span>
                              <SeverityMix counts={s.by_severity} total={s.findings_total} />
                            </span>
                          ) : (
                            <span className="text-faint">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted">
                          {s ? (
                            <>
                              <span className="numeric">{s.files_changed} files</span> · {s.mode === "full_context" ? "full context" : "diff only"}
                              {s.patch_coverage != null && <> · {s.patch_coverage}% covered</>}
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-xs text-muted">
                          <RelativeTime iso={item.created_at} />
                          {item.duration_ms != null && <span className="text-faint"> · {formatDuration(item.duration_ms)}</span>}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            type="button"
                            onClick={() => remove(item.id)}
                            disabled={removing === item.id}
                            className="rounded-md px-2 py-1 text-xs text-muted opacity-100 transition-opacity hover:bg-danger-tint hover:text-danger disabled:opacity-40 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100"
                            aria-label={`Delete report ${item.title}`}
                          >
                            Delete
                          </button>
                        </td>
                      </motion.tr>
                    );
                  })}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        )}
        {list.data && list.data.total > items.length && (
          <p className="mt-3 text-xs text-muted">Showing the {items.length} most recent of {list.data.total} reports.</p>
        )}
      </div>
    </div>
  );
}
