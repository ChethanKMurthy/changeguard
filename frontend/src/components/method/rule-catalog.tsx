"use client";

import { useDeferredValue, useMemo, useState } from "react";

import type { RuleInfo } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { CATEGORY_LABEL, PROVENANCE_META, SEVERITY_LABEL } from "@/lib/format";
import { renderInlineCode } from "@/lib/inline-code";

import { SeverityMark } from "../ui/badges";

type SourceFilter = "all" | "changeguard" | "ruff";
type KindFilter = "all" | "deterministic" | "heuristic";

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; count: number }[];
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-md border border-line bg-bg p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "inline-flex h-7 items-center gap-1.5 rounded-[5px] px-2.5 text-[0.75rem] transition-colors duration-150",
            value === option.value ? "bg-ink text-bg" : "text-muted hover:text-ink",
          )}
        >
          {option.label}
          <span className={cn("numeric text-[0.625rem]", value === option.value ? "text-bg/70" : "text-faint")}>{option.count}</span>
        </button>
      ))}
    </div>
  );
}

/** Every rule the engine can report, searchable, with a stable anchor per rule (#rule-<id>). */
export function RuleCatalog({ rules }: { rules: RuleInfo[] }) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<SourceFilter>("all");
  const [kind, setKind] = useState<KindFilter>("all");
  const deferred = useDeferredValue(query.trim().toLowerCase());

  const visible = useMemo(
    () =>
      rules.filter((rule) => {
        if (source !== "all" && rule.source !== source) return false;
        if (kind !== "all" && rule.kind !== kind) return false;
        if (!deferred) return true;
        const haystack = `${rule.id} ${rule.title} ${rule.rationale} ${rule.category} ${CATEGORY_LABEL[rule.category] ?? ""} ${rule.languages.join(" ")}`.toLowerCase();
        return haystack.includes(deferred);
      }),
    [rules, source, kind, deferred],
  );

  const count = (pred: (r: RuleInfo) => boolean) => rules.filter(pred).length;

  return (
    <div className="rounded-[14px] border border-line bg-raised">
      <div className="flex flex-wrap items-center gap-3 border-b border-line p-3 sm:p-4">
        <label className="relative min-w-[200px] flex-1">
          <span className="sr-only">Search rules</span>
          <svg viewBox="0 0 16 16" className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by ID, title, category, language"
            className="h-9 w-full rounded-md border border-line-strong bg-bg pl-8 pr-3 text-[0.8125rem] text-ink placeholder:text-muted focus-visible:outline-2 focus-visible:outline-offset-1"
          />
        </label>
        <Segmented
          label="Rule source"
          value={source}
          onChange={setSource}
          options={[
            { value: "all", label: "All", count: rules.length },
            { value: "changeguard", label: "ChangeGuard", count: count((r) => r.source === "changeguard") },
            { value: "ruff", label: "Ruff", count: count((r) => r.source === "ruff") },
          ]}
        />
        <Segmented
          label="Provenance"
          value={kind}
          onChange={setKind}
          options={[
            { value: "all", label: "Any", count: rules.length },
            { value: "deterministic", label: "◆ Deterministic", count: count((r) => r.kind === "deterministic") },
            { value: "heuristic", label: "◇ Heuristic", count: count((r) => r.kind === "heuristic") },
          ]}
        />
      </div>
      <p className="sr-only" aria-live="polite">
        {visible.length} rules shown
      </p>
      {visible.length === 0 ? (
        <p className="px-4 py-10 text-center text-[0.875rem] text-muted">No rule matches that search.</p>
      ) : (
        <ul className="divide-y divide-line">
          {visible.map((rule) => (
            <li
              key={rule.id}
              id={`rule-${rule.id}`}
              className="grid scroll-mt-28 gap-x-6 gap-y-1.5 px-4 py-3.5 transition-colors duration-500 target:bg-signal-tint sm:grid-cols-[148px_minmax(0,1fr)_auto]"
            >
              <div className="flex items-center gap-2 sm:block">
                <a href={`#rule-${rule.id}`} className="font-mono text-[0.75rem] font-semibold text-ink hover:text-signal">
                  {rule.id}
                </a>
                <span className="block text-[0.6875rem] text-muted sm:mt-0.5">{rule.source === "ruff" ? "Ruff, differential" : "ChangeGuard"}</span>
              </div>
              <div className="min-w-0">
                <p className="text-[0.875rem] font-medium text-ink">{renderInlineCode(rule.title)}</p>
                <p className="mt-0.5 text-[0.8125rem] leading-relaxed text-ink-soft">{renderInlineCode(rule.rationale)}</p>
                <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[0.6875rem] text-muted">
                  <span>{CATEGORY_LABEL[rule.category] ?? rule.category}</span>
                  <span>{rule.languages.length ? rule.languages.join(", ") : "any file"}</span>
                </p>
              </div>
              <div className="flex items-center gap-3 text-[0.6875rem] text-muted sm:flex-col sm:items-end sm:gap-1">
                <span className="flex items-center gap-1.5">
                  <SeverityMark severity={rule.default_severity} />
                  {SEVERITY_LABEL[rule.default_severity]}
                </span>
                <span title={PROVENANCE_META[rule.kind].description}>
                  <span aria-hidden="true">{PROVENANCE_META[rule.kind].glyph}</span> {PROVENANCE_META[rule.kind].label}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
