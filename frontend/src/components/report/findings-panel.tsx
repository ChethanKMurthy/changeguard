"use client";

import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";

import type { Category, Evidence, Finding, Provenance, Severity } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { CATEGORY_LABEL, PROVENANCE_META, PROVENANCE_ORDER, SEVERITY_LABEL, SEVERITY_ORDER } from "@/lib/format";

import { ConfidenceMeter, ProvenanceGlyph, SeverityMark } from "../ui/badges";
import { FindingInspector } from "./finding-inspector";
import { renderInlineCode } from "./evidence";

type Filters = { severities: Set<Severity>; kinds: Set<Provenance>; category: Category | "all"; query: string };

function FilterChip({
  active,
  onClick,
  children,
  count,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  count?: number;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-[0.8125rem] transition-colors duration-150 disabled:opacity-40",
        active ? "border-ink bg-ink text-bg" : "border-line bg-bg text-ink-soft hover:border-line-strong hover:text-ink",
      )}
    >
      {children}
      {count !== undefined && <span className={cn("numeric text-[0.6875rem]", active ? "text-bg/70" : "text-faint")}>{count}</span>}
    </button>
  );
}

function toggle<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export function FindingsPanel({
  findings,
  evidence,
  selectedId,
  onSelect,
  onShowInDiff,
}: {
  findings: Finding[];
  evidence: Map<string, Evidence>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onShowInDiff: (finding: Finding) => void;
}) {
  const reduce = useReducedMotion();
  const [filters, setFilters] = useState<Filters>({ severities: new Set(), kinds: new Set(), category: "all", query: "" });
  const [sheetOpen, setSheetOpen] = useState(false);

  const categories = useMemo(() => [...new Set(findings.map((f) => f.category))].sort(), [findings]);
  const visible = useMemo(() => {
    const q = filters.query.trim().toLowerCase();
    return findings.filter(
      (f) =>
        (filters.severities.size === 0 || filters.severities.has(f.severity)) &&
        (filters.kinds.size === 0 || filters.kinds.has(f.kind)) &&
        (filters.category === "all" || f.category === filters.category) &&
        (!q || `${f.title} ${f.location.file} ${f.rule_id} ${f.description}`.toLowerCase().includes(q)),
    );
  }, [findings, filters]);

  const groups = SEVERITY_ORDER.map((severity) => ({ severity, items: visible.filter((f) => f.severity === severity) })).filter(
    (g) => g.items.length > 0,
  );
  const selected = findings.find((f) => f.id === selectedId) ?? visible[0] ?? null;
  const hasFilters = filters.severities.size > 0 || filters.kinds.size > 0 || filters.category !== "all" || filters.query !== "";

  useEffect(() => {
    if (!sheetOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSheetOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheetOpen]);

  // Keyboard navigation between findings (j / k), matching code-review tools.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA")) return;
      if (e.key !== "j" && e.key !== "k") return;
      const ordered = groups.flatMap((g) => g.items);
      if (!ordered.length) return;
      const index = ordered.findIndex((f) => f.id === selected?.id);
      const next = ordered[Math.max(0, Math.min(ordered.length - 1, index + (e.key === "j" ? 1 : -1)))];
      onSelect(next.id);
      document.getElementById(`finding-${next.id}`)?.scrollIntoView({ block: "nearest" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [groups, selected?.id, onSelect]);

  if (findings.length === 0) {
    return (
      <div className="rounded-[10px] border border-line bg-surface px-6 py-14 text-center">
        <p className="text-lg font-semibold">No findings</p>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
          None of the rules matched this change. That is a statement about the rules, not a guarantee: read the limitations
          tab for what was and was not checked.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.15fr)] lg:gap-8">
      <div className="min-w-0">
        <div className="space-y-3" role="group" aria-label="Filter findings">
          <div className="flex flex-wrap gap-1.5">
            {SEVERITY_ORDER.map((severity) => {
              const count = findings.filter((f) => f.severity === severity).length;
              if (!count) return null;
              return (
                <FilterChip
                  key={severity}
                  active={filters.severities.has(severity)}
                  count={count}
                  onClick={() => setFilters((f) => ({ ...f, severities: toggle(f.severities, severity) }))}
                >
                  <SeverityMark severity={severity} className={filters.severities.has(severity) ? "!text-bg" : undefined} />
                  {SEVERITY_LABEL[severity]}
                </FilterChip>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {PROVENANCE_ORDER.map((kind) => {
              const count = findings.filter((f) => f.kind === kind).length;
              return (
                <FilterChip
                  key={kind}
                  active={filters.kinds.has(kind)}
                  count={count}
                  disabled={!count}
                  onClick={() => setFilters((f) => ({ ...f, kinds: toggle(f.kinds, kind) }))}
                >
                  <span aria-hidden="true" className="text-[0.6875rem]">{PROVENANCE_META[kind].glyph}</span>
                  {PROVENANCE_META[kind].label}
                </FilterChip>
              );
            })}
          </div>
          <div className="flex gap-2">
            <label className="relative flex-1">
              <span className="sr-only">Search findings</span>
              <input
                type="search"
                value={filters.query}
                onChange={(e) => setFilters((f) => ({ ...f, query: e.target.value }))}
                placeholder="Search title, file, or rule"
                className="h-9 w-full rounded-md border border-line bg-bg px-3 text-sm placeholder:text-muted focus:border-ink focus:outline-none"
              />
            </label>
            <label>
              <span className="sr-only">Category</span>
              <select
                value={filters.category}
                onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value as Category | "all" }))}
                className="h-9 rounded-md border border-line bg-bg px-2.5 text-sm text-ink focus:border-ink focus:outline-none"
              >
                <option value="all">All categories</option>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABEL[c]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="flex items-center justify-between text-xs text-muted" aria-live="polite">
            <span>
              Showing <span className="numeric font-medium text-ink">{visible.length}</span> of {findings.length} findings
            </span>
            {hasFilters ? (
              <button type="button" className="underline underline-offset-2 hover:text-ink" onClick={() => setFilters({ severities: new Set(), kinds: new Set(), category: "all", query: "" })}>
                Clear filters
              </button>
            ) : (
              <span className="hidden sm:inline">
                <kbd className="font-mono">j</kbd>/<kbd className="font-mono">k</kbd> to move
              </span>
            )}
          </p>
        </div>

        <LayoutGroup>
          <div className="mt-4 space-y-5">
            {groups.map((group) => (
              <motion.section key={group.severity} layout={reduce ? false : "position"} aria-label={`${SEVERITY_LABEL[group.severity]} severity`}>
                <h3 className="mb-1.5 flex items-center gap-2 px-1 text-xs font-semibold text-muted">
                  <SeverityMark severity={group.severity} />
                  {SEVERITY_LABEL[group.severity]}
                  <span className="numeric font-normal text-faint">{group.items.length}</span>
                </h3>
                <ul className="space-y-1">
                  <AnimatePresence initial={false}>
                    {group.items.map((finding) => {
                      const active = finding.id === selected?.id;
                      return (
                        <motion.li
                          key={finding.id}
                          id={`finding-${finding.id}`}
                          layout={reduce ? false : "position"}
                          initial={reduce ? false : { opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                        >
                          <button
                            type="button"
                            aria-current={active ? "true" : undefined}
                            onClick={() => {
                              onSelect(finding.id);
                              if (window.matchMedia("(max-width: 1023px)").matches) setSheetOpen(true);
                            }}
                            className={cn(
                              "group w-full rounded-[10px] border px-3.5 py-3 text-left transition-colors duration-150",
                              active ? "border-ink/80 bg-surface" : "border-transparent hover:border-line hover:bg-surface/60",
                            )}
                          >
                            <span className="flex items-start gap-2.5">
                              <ProvenanceGlyph kind={finding.kind} className="mt-[3px] w-3 shrink-0 text-center text-[0.75rem]" />
                              <span className="min-w-0 flex-1">
                                <span className="line-clamp-2 text-[0.9rem] font-medium leading-snug text-ink">{renderInlineCode(finding.title)}</span>
                                <span className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted">
                                  <span className="truncate font-mono text-[0.6875rem]">
                                    {finding.location.file}
                                    {finding.location.start_line ? `:${finding.location.start_line}` : ""}
                                  </span>
                                  <ConfidenceMeter confidence={finding.confidence} className="text-[0.6875rem]" />
                                </span>
                              </span>
                            </span>
                          </button>
                        </motion.li>
                      );
                    })}
                  </AnimatePresence>
                </ul>
              </motion.section>
            ))}
            {groups.length === 0 && (
              <p className="rounded-[10px] border border-dashed border-line px-4 py-10 text-center text-sm text-muted">
                No findings match these filters.
              </p>
            )}
          </div>
        </LayoutGroup>
      </div>

      <aside className="hidden min-w-0 lg:block">
        <div className="sticky top-24 max-h-[calc(100dvh-7rem)] overflow-y-auto rounded-[12px] border border-line bg-bg p-5 scrollbar-thin">
          {selected ? <FindingInspector finding={selected} evidence={evidence} onShowInDiff={onShowInDiff} /> : null}
        </div>
      </aside>

      <AnimatePresence>
        {sheetOpen && selected && (
          <motion.div
            className="fixed inset-0 z-50 flex flex-col bg-bg lg:hidden"
            initial={reduce ? { opacity: 0 } : { y: "100%" }}
            animate={reduce ? { opacity: 1 } : { y: 0 }}
            exit={reduce ? { opacity: 0 } : { y: "100%" }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            role="dialog"
            aria-modal="true"
            aria-label="Finding details"
          >
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <span className="text-sm font-semibold">Finding</span>
              <button type="button" onClick={() => setSheetOpen(false)} className="rounded-md px-2 py-1 text-sm text-muted hover:bg-surface-2 hover:text-ink">
                Close
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-5">
              <FindingInspector
                finding={selected}
                evidence={evidence}
                onShowInDiff={(f) => {
                  setSheetOpen(false);
                  onShowInDiff(f);
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
