"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";

import { cn } from "@/lib/cn";
import type { RulesFigure } from "@/lib/experience-data";

import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;

/** Fig. 7: every rule family and what it found on the added lines, zeros included. */
export function FigRules({ data, docstring }: { data: RulesFigure; docstring: { line: number; text: string } | null }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.3 });
  const play = !reduce && inView;
  const hits = data.families.filter((f) => f.count > 0).length;
  const excerpt = data.logicEvidence?.excerpt?.split("\n") ?? [];

  return (
    <Plate label="risk rules · added lines" meta={`${data.families.length} families · ${hits} with matches`}>
      <div ref={ref} className="grid sm:grid-cols-2">
        {data.families.map((family, i) => (
          <motion.div
            key={family.label}
            initial={play ? { opacity: 0 } : false}
            animate={play ? { opacity: 1 } : undefined}
            transition={{ duration: 0.3, delay: i * 0.05 }}
            className={cn(
              "flex items-center justify-between gap-3 border-b border-line px-4 py-2.5 sm:[&:nth-child(odd)]:border-r",
              family.count > 0 && "bg-signal-tint",
            )}
          >
            <span className={cn("text-[0.8125rem]", family.count > 0 ? "font-medium text-ink" : "text-ink-soft")}>{family.label}</span>
            <span className="flex items-center gap-2">
              <span className={cn("text-[0.6875rem]", family.count > 0 ? "text-signal" : "text-faint")}>{family.count > 0 ? "match" : "clear"}</span>
              <motion.span
                className={cn(
                  "inline-flex h-6 min-w-6 items-center justify-center rounded-[5px] font-mono text-[0.75rem] font-semibold numeric",
                  family.count > 0 ? "bg-signal text-white dark:text-bg" : "bg-surface-2 text-muted",
                )}
                initial={play && family.count > 0 ? { scale: 0.6 } : false}
                animate={play && family.count > 0 ? { scale: 1 } : undefined}
                transition={{ duration: 0.35, delay: 0.6 + i * 0.05, ease: EASE }}
              >
                {family.count}
              </motion.span>
            </span>
          </motion.div>
        ))}
        {data.families.length % 2 === 1 && (
          <div className="hidden items-center border-b border-line px-4 py-2.5 text-[0.75rem] text-muted sm:flex">
            Python lint rules (Ruff) are counted in chapter 04.
          </div>
        )}
      </div>

      {data.logic && data.logicEvidence && (
        <div className="grid gap-5 p-4 sm:p-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="min-w-0">
            <p className="mb-2 text-[0.6875rem] font-medium text-muted">
              The one match · {data.logicEvidence.file}:{data.logicEvidence.start_line} · {data.logicEvidence.id}
            </p>
            <div className="relative overflow-x-auto rounded-[8px] border border-line font-mono text-[0.75rem] leading-[1.8] scrollbar-thin">
              {docstring && (
                <div className="flex gap-3 bg-highlight/60 px-3">
                  <span className="w-5 shrink-0 select-none text-right text-faint numeric">{docstring.line}</span>
                  <span className="select-none text-transparent"> </span>
                  <span className="whitespace-pre-wrap text-ink-soft">{docstring.text}</span>
                </div>
              )}
              {excerpt.map((row, i) => {
                const add = row.startsWith("+");
                return (
                  <div key={i} className={cn("flex gap-3 px-3", add ? "bg-diff-add" : "bg-diff-del")}>
                    <span className="w-5 shrink-0 select-none text-right text-faint numeric">
                      {add ? String(data.logicEvidence?.data.new_line ?? "") : String(data.logicEvidence?.data.old_line ?? "")}
                    </span>
                    <span className={cn("select-none", add ? "text-ok" : "text-danger")}>{add ? "+" : "−"}</span>
                    <span className="whitespace-pre">{row.slice(1).trimStart()}</span>
                  </div>
                );
              })}
            </div>
            {docstring && (
              <p className="mt-2 text-[0.75rem] text-muted">
                Highlighted: the unchanged docstring, line {docstring.line}, which still says <em>above</em>.
              </p>
            )}
          </div>
          <div className="min-w-0 rounded-[10px] border border-line bg-surface p-3.5">
            <p className="flex items-center gap-2 text-[0.6875rem] text-muted">
              <span className="font-semibold text-ink" aria-hidden="true">◇</span> Heuristic · {data.logic.rule_id}
            </p>
            <p className="mt-1.5 text-[0.875rem] font-medium text-ink">Condition logic changed</p>
            <dl className="mt-3 grid grid-cols-[88px_1fr] gap-y-1.5 text-[0.75rem]">
              <dt className="text-muted">Severity</dt>
              <dd className="text-ink">{data.logic.severity}</dd>
              <dt className="text-muted">Confidence</dt>
              <dd className="text-ink">{data.logic.confidence}</dd>
            </dl>
            {data.suggestion && (
              <p className="mt-3 border-t border-line pt-3 text-[0.75rem] leading-relaxed text-ink-soft">
                <span className="font-medium text-ink">Suggested check. </span>
                {data.suggestion}
              </p>
            )}
          </div>
        </div>
      )}
    </Plate>
  );
}
