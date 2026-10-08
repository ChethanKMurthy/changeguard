"use client";

import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useRef, useState } from "react";

import type { Provenance, Severity } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import type { MatrixFigure } from "@/lib/experience-data";
import { CATEGORY_LABEL, PRIORITY_META, PROVENANCE_META, PROVENANCE_ORDER, SEVERITY_LABEL } from "@/lib/format";
import { renderInlineCode } from "@/lib/inline-code";

import { SeverityMark } from "../ui/badges";
import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;
const ROWS: Severity[] = ["critical", "high", "medium", "low"];

const LADDER: { level: string; rule: string }[] = [
  { level: "block", rule: "A critical finding established by deterministic analysis." },
  { level: "high", rule: "Any high-severity deterministic or heuristic finding." },
  { level: "elevated", rule: "Any medium-severity finding. AI findings alone can raise priority this far and no further." },
  { level: "routine", rule: "Only low-severity or informational findings." },
];

/** Fig. 10: every finding placed by severity and provenance, and the transparent rule that sets review priority. */
export function FigMatrix({ data }: { data: MatrixFigure }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.3 });
  const play = !reduce && inView;
  const triggered = new Set(data.priority.triggered_by);
  const [selected, setSelected] = useState<string | null>(data.priority.triggered_by[0] ?? data.findings[0]?.id ?? null);
  const chosen = data.findings.find((f) => f.id === selected);
  let order = 0;

  const cell = (severity: Severity, kind: Provenance) => data.findings.filter((f) => f.severity === severity && f.kind === kind);

  return (
    <Plate label="report · severity × provenance" meta={`${data.findings.length} findings · priority ${PRIORITY_META[data.priority.level]?.label}`}>
      <div ref={ref} className="grid lg:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)]">
        <div className="border-b border-line p-3 sm:p-5 lg:border-b-0 lg:border-r">
          <table className="w-full table-fixed border-collapse">
            <caption className="sr-only">Findings by severity (rows) and provenance (columns). Select a finding to read it.</caption>
            <thead>
              <tr>
                <th scope="col" className="w-[64px] sm:w-[84px]" />
                {PROVENANCE_ORDER.map((kind) => (
                  <th key={kind} scope="col" className="px-1 pb-2 text-left text-[0.625rem] font-medium leading-tight text-muted sm:px-1.5 sm:text-[0.6875rem]">
                    <span className={cn("mr-1", kind === "ai" && "text-ai")} aria-hidden="true">
                      {PROVENANCE_META[kind].glyph}
                    </span>
                    {PROVENANCE_META[kind].label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((severity) => (
                <tr key={severity}>
                  <th scope="row" className="py-1 pr-1 text-left align-middle text-[0.6875rem] font-medium text-ink-soft sm:pr-2 sm:text-[0.75rem]">
                    <span className="flex items-center gap-1.5">
                      <SeverityMark severity={severity} />
                      {SEVERITY_LABEL[severity]}
                    </span>
                  </th>
                  {PROVENANCE_ORDER.map((kind) => {
                    const items = cell(severity, kind);
                    return (
                      <td key={kind} className="p-1 align-top">
                        <div
                          className={cn(
                            "flex min-h-[48px] flex-wrap content-start items-start gap-1 rounded-[8px] border p-1.5 sm:min-h-[52px] sm:gap-1.5 sm:p-2",
                            items.length ? "border-line bg-surface" : "border-dashed border-line",
                          )}
                        >
                          {items.length === 0 && <span className="text-[0.6875rem] text-faint">0</span>}
                          {items.map((f) => {
                            const delay = (order++) * 0.045;
                            return (
                              <motion.button
                                key={f.id}
                                type="button"
                                onClick={() => setSelected(f.id)}
                                aria-pressed={selected === f.id}
                                aria-label={`${SEVERITY_LABEL[f.severity]} ${PROVENANCE_META[f.kind].label.toLowerCase()} finding: ${f.title.replace(/`/g, "")}`}
                                title={f.title.replace(/`/g, "")}
                                className={cn(
                                  "flex size-6 items-center justify-center rounded-[6px] border bg-bg transition-[box-shadow,border-color] duration-150 sm:size-7",
                                  selected === f.id ? "border-ink shadow-[0_0_0_2px_var(--signal-tint-strong)]" : "border-line-strong hover:border-ink",
                                  triggered.has(f.id) && "ring-2 ring-signal ring-offset-1 ring-offset-bg",
                                )}
                                initial={play ? { opacity: 0, y: -6 } : false}
                                animate={play ? { opacity: 1, y: 0 } : undefined}
                                transition={{ duration: 0.3, delay: 0.1 + delay, ease: EASE }}
                              >
                                <SeverityMark severity={f.severity} className="size-3" />
                              </motion.button>
                            );
                          })}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 flex items-center gap-2 text-[0.75rem] text-muted">
            <span className="inline-block size-3.5 rounded-[4px] border border-line-strong ring-2 ring-signal ring-offset-1 ring-offset-bg" aria-hidden="true" />
            sets the review priority
          </p>
        </div>

        <div className="p-4 sm:p-5">
          <h3 className="text-[0.8125rem] font-semibold text-ink">Review priority</h3>
          <p className="mt-0.5 text-[0.75rem] text-muted">First rule that matches, top to bottom. A triage label, not a probability.</p>
          <ol className="mt-4 space-y-1.5">
            {LADDER.map((step) => {
              const current = step.level === data.priority.level;
              return (
                <li
                  key={step.level}
                  className={cn(
                    "rounded-[8px] border px-3 py-2 transition-colors",
                    current ? "border-signal/50 bg-signal-tint" : "border-transparent",
                  )}
                  aria-current={current ? "step" : undefined}
                >
                  <p className={cn("text-[0.8125rem] font-semibold", current ? "text-signal" : "text-ink-soft")}>
                    {PRIORITY_META[step.level]?.label}
                    {current && <span className="ml-2 text-[0.6875rem] font-normal text-muted">this change</span>}
                  </p>
                  <p className="text-[0.75rem] leading-relaxed text-muted">{step.rule}</p>
                </li>
              );
            })}
          </ol>
        </div>
      </div>

      <div className="min-h-[76px] border-t border-line bg-surface px-4 py-3 sm:px-5" aria-live="polite">
        <AnimatePresence mode="wait" initial={false}>
          {chosen && (
            <motion.div
              key={chosen.id}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: EASE }}
              className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2"
            >
              <div className="min-w-0">
                <p className="text-[0.8125rem] font-medium text-ink">{renderInlineCode(chosen.title)}</p>
                <p className="mt-0.5 font-mono text-[0.625rem] text-faint">
                  {chosen.file}
                  {chosen.line ? `:${chosen.line}` : ""} · {chosen.rule_id} · {CATEGORY_LABEL[chosen.category]} · confidence {chosen.confidence}
                </p>
              </div>
              <Link
                href={`/reports/sample#${chosen.id}`}
                className="shrink-0 text-[0.8125rem] font-medium text-ink underline decoration-line-strong underline-offset-[3px] hover:decoration-signal"
              >
                Read it with its evidence →
              </Link>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Plate>
  );
}
