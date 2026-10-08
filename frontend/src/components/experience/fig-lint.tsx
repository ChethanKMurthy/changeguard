"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";

import { cn } from "@/lib/cn";
import type { LintFigure } from "@/lib/experience-data";
import { SEVERITY_LABEL } from "@/lib/format";
import { renderInlineCode } from "@/lib/inline-code";

import { SeverityMark } from "../ui/badges";
import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;
const ROW = 60;
const CARD = 48;
const GAP_W = 76;

/** Fig. 6: new diagnostics in the head revision, and the findings they become after de-duplication. */
export function FigLint({ data }: { data: LintFigure }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.35 });
  const play = !reduce && inView;

  const diags = [...data.diagnostics].sort((a, b) => a.file.localeCompare(b.file) || (a.line ?? 0) - (b.line ?? 0) || a.code.localeCompare(b.code));
  const findingFor = (evidenceId: string) => data.findings.find((f) => f.evidence_ids.includes(evidenceId));
  const rowOf = new Map(diags.map((d, i) => [d.evidenceId, i]));
  const findings = data.findings
    .map((f) => {
      const rows = f.evidence_ids.map((id) => rowOf.get(id)).filter((r): r is number => r !== undefined);
      const center = rows.length ? (rows.reduce((a, b) => a + b, 0) / rows.length) * ROW + ROW / 2 : 0;
      return { finding: f, rows, center };
    })
    .sort((a, b) => a.center - b.center);
  const height = diags.length * ROW;

  return (
    <Plate label={`differential lint · ${data.tool}`} meta={`${diags.length} new diagnostics → ${findings.length} findings`}>
      <div ref={ref} className="p-4 sm:p-5">
        <div className="mb-2 hidden grid-cols-[minmax(0,1fr)_76px_minmax(0,1fr)] text-[0.6875rem] font-medium text-muted md:grid">
          <span>New in head (absent from base)</span>
          <span />
          <span>Findings after de-duplication</span>
        </div>

        {/* Desktop: connectors show which diagnostics became which finding */}
        <div className="relative hidden grid-cols-[minmax(0,1fr)_76px_minmax(0,1fr)] md:grid" style={{ height }}>
          <ul>
            {diags.map((d, i) => (
              <motion.li
                key={d.evidenceId}
                style={{ height: ROW }}
                className="flex items-center"
                initial={play ? { opacity: 0, x: -6 } : false}
                animate={play ? { opacity: 1, x: 0 } : undefined}
                transition={{ duration: 0.35, delay: i * 0.07, ease: EASE }}
              >
                <div className="flex w-full min-w-0 items-center gap-2.5 rounded-[8px] border border-line bg-bg px-2.5 py-2">
                  <span className="shrink-0 rounded-[4px] bg-surface-2 px-1.5 py-px font-mono text-[0.625rem] font-semibold text-ink">{d.code}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.75rem] text-ink">{renderInlineCode(d.message)}</span>
                    <span className="block font-mono text-[0.625rem] text-faint">
                      {d.file.split("/").pop()}:{d.line} · {d.evidenceId}
                    </span>
                  </span>
                </div>
              </motion.li>
            ))}
          </ul>
          <svg viewBox={`0 0 ${GAP_W} ${height}`} preserveAspectRatio="none" className="h-full w-full" aria-hidden="true">
            {diags.map((d, i) => {
              const f = findingFor(d.evidenceId);
              const target = findings.find((x) => x.finding.id === f?.id);
              if (!target) return null;
              const y1 = i * ROW + ROW / 2;
              const y2 = target.center;
              const merged = target.rows.length > 1;
              return (
                <motion.path
                  key={d.evidenceId}
                  d={`M2 ${y1} C ${GAP_W * 0.5} ${y1}, ${GAP_W * 0.5} ${y2}, ${GAP_W - 2} ${y2}`}
                  fill="none"
                  vectorEffect="non-scaling-stroke"
                  className={merged ? "stroke-signal" : "stroke-line-strong"}
                  strokeWidth={merged ? 1.6 : 1.2}
                  initial={play ? { pathLength: 0 } : false}
                  animate={play ? { pathLength: 1 } : undefined}
                  transition={{ duration: 0.45, delay: 0.45 + i * 0.07, ease: EASE }}
                />
              );
            })}
          </svg>
          <div className="relative">
            {findings.map(({ finding, rows, center }, i) => (
              <motion.div
                key={finding.id}
                className={cn(
                  "absolute inset-x-0 flex items-center gap-2.5 rounded-[8px] border px-2.5",
                  rows.length > 1 ? "border-signal/50 bg-signal-tint" : "border-line bg-bg",
                )}
                style={{ top: center - CARD / 2, height: CARD }}
                initial={play ? { opacity: 0, x: 6 } : false}
                animate={play ? { opacity: 1, x: 0 } : undefined}
                transition={{ duration: 0.35, delay: 0.8 + i * 0.07, ease: EASE }}
              >
                <SeverityMark severity={finding.severity} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.75rem] font-medium text-ink">{renderInlineCode(finding.title)}</span>
                  <span className="block truncate font-mono text-[0.625rem] text-faint">
                    {finding.rule_id} · {SEVERITY_LABEL[finding.severity].toLowerCase()}
                    {finding.corroborated_by.length > 0 && <span className="text-signal"> · corroborated by {finding.corroborated_by.join(", ")}</span>}
                  </span>
                </span>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Mobile: grouped by finding */}
        <ul className="space-y-3 md:hidden">
          {findings.map(({ finding, rows }) => (
            <li key={finding.id} className={cn("rounded-[8px] border p-3", rows.length > 1 ? "border-signal/50 bg-signal-tint" : "border-line bg-bg")}>
              <p className="flex items-start gap-2 text-[0.8125rem] font-medium text-ink">
                <SeverityMark severity={finding.severity} className="mt-1" />
                <span>{renderInlineCode(finding.title)}</span>
              </p>
              <ul className="mt-2 space-y-1">
                {rows.map((r) => (
                  <li key={diags[r].evidenceId} className="font-mono text-[0.6875rem] text-muted">
                    {diags[r].code} · {diags[r].file.split("/").pop()}:{diags[r].line} · {diags[r].evidenceId}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </div>
      <div className="border-t border-line bg-surface px-4 py-2.5 text-[0.75rem] leading-relaxed text-muted">
        Diagnostics are matched across revisions by rule code and normalised source line, so code that merely moved is not reported as new.
      </div>
    </Plate>
  );
}
