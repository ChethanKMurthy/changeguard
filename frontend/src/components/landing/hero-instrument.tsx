"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";

import type { Provenance, Severity } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDuration, SEVERITY_LABEL } from "@/lib/format";

import { ProvenanceGlyph, SeverityMark } from "../ui/badges";

export interface InstrumentData {
  file: string;
  diff: { kind: "add" | "del" | "context"; text: string; line: number | null }[];
  stages: { label: string; ms: number }[];
  findings: { title: string; severity: Severity; kind: Provenance; where: string }[];
  totalFindings: number;
  totalMs: number;
}

const EASE = [0.22, 1, 0.36, 1] as const;

function strip(text: string) {
  return text.replace(/`/g, "");
}

/**
 * Fig. 1 on the landing page: a replay of a real analysis of the billing sample.
 * The diff is read, the signal trace runs through the stages, and the findings land.
 */
export function HeroInstrument({ data }: { data: InstrumentData }) {
  const reduce = useReducedMotion();
  const [run, setRun] = useState(0);
  const animate = !reduce;
  const diffDelay = (i: number) => (animate ? 0.25 + i * 0.12 : 0);
  const stageStart = animate ? 0.25 + data.diff.length * 0.12 + 0.2 : 0;
  const stageStep = 0.16;
  const findingsStart = animate ? stageStart + data.stages.length * stageStep + 0.15 : 0;

  return (
    <div className="relative">
      <div className="lab-grid absolute -inset-3 rounded-[18px] opacity-60 [mask-image:radial-gradient(ellipse_at_center,black_45%,transparent_78%)]" aria-hidden="true" />
      <div key={run} className="relative overflow-hidden rounded-[14px] border border-line-strong bg-raised shadow-float">
        {/* Header: the specimen */}
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
          <span className="flex items-center gap-2 font-mono text-[0.6875rem] text-muted">
            <span className="size-1.5 rounded-full bg-signal-glow" aria-hidden="true" />
            {data.file}
          </span>
          <span className="font-mono text-[0.625rem] text-faint">SAMPLE · SYNTHETIC</span>
        </div>

        {/* The change */}
        <div className="border-b border-line py-2 font-mono text-[0.72rem] leading-[1.75]">
          {data.diff.map((row, i) => (
            <motion.div
              key={i}
              initial={animate ? { opacity: 0, x: -6 } : false}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.35, delay: diffDelay(i), ease: EASE }}
              className={cn("flex gap-3 px-4", row.kind === "add" && "bg-diff-add", row.kind === "del" && "bg-diff-del")}
            >
              <span className="w-6 shrink-0 select-none text-right text-faint numeric">{row.line ?? ""}</span>
              <span className={cn("select-none", row.kind === "add" ? "text-ok" : row.kind === "del" ? "text-danger" : "text-transparent")}>
                {row.kind === "add" ? "+" : row.kind === "del" ? "−" : " "}
              </span>
              <span className="truncate whitespace-pre">{row.text}</span>
            </motion.div>
          ))}
        </div>

        {/* The instrument: stages with a travelling signal trace */}
        <div className="border-b border-line px-4 py-3.5">
          <div className="relative">
            <span className="absolute left-0 right-0 top-[5px] h-px bg-line" aria-hidden="true" />
            <motion.span
              className="absolute left-0 top-[4.5px] h-[2px] origin-left rounded-full bg-signal-glow"
              style={{ width: "100%" }}
              initial={animate ? { scaleX: 0 } : false}
              animate={{ scaleX: 1 }}
              transition={{ duration: data.stages.length * stageStep, delay: stageStart, ease: "linear" }}
              aria-hidden="true"
            />
            <ol className="relative flex justify-between" aria-label="Pipeline stages">
              {data.stages.map((stage, i) => (
                <li key={stage.label} className="flex flex-col items-center">
                  <motion.span
                    className="size-[11px] rounded-[3px] border border-ink bg-ink"
                    initial={animate ? { backgroundColor: "var(--bg)", borderColor: "var(--line-strong)" } : false}
                    animate={{ backgroundColor: "var(--ink)", borderColor: "var(--ink)" }}
                    transition={{ duration: 0.2, delay: stageStart + (i + 1) * stageStep - 0.05 }}
                  />
                </li>
              ))}
            </ol>
          </div>
          <div className="mt-2.5 flex items-baseline justify-between gap-3 text-[0.6875rem] text-muted">
            <span>{data.stages.length} stages · Ruff, tree-sitter, coverage</span>
            <motion.span
              className="font-mono text-ink numeric"
              initial={animate ? { opacity: 0 } : false}
              animate={{ opacity: 1 }}
              transition={{ delay: findingsStart - 0.1, duration: 0.3 }}
            >
              {formatDuration(data.totalMs)}
            </motion.span>
          </div>
        </div>

        {/* The findings */}
        <ul className="divide-y divide-line">
          <AnimatePresence>
            {data.findings.map((f, i) => (
              <motion.li
                key={f.title}
                initial={animate ? { opacity: 0, y: 10 } : false}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: findingsStart + i * 0.16, ease: EASE }}
                className="flex items-start gap-3 px-4 py-2.5"
              >
                <ProvenanceGlyph kind={f.kind} className="mt-px w-3 shrink-0 text-center text-[0.75rem]" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[0.8125rem] font-medium text-ink">{strip(f.title)}</span>
                  <span className="mt-0.5 block truncate font-mono text-[0.625rem] text-faint">{f.where}</span>
                </span>
                <span className="mt-0.5 flex shrink-0 items-center gap-1.5 text-[0.6875rem] text-muted">
                  <SeverityMark severity={f.severity} />
                  {SEVERITY_LABEL[f.severity]}
                </span>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
        <div className="flex items-center justify-between gap-3 border-t border-line bg-surface px-4 py-2">
          <span className="text-[0.6875rem] text-muted">
            +{data.totalFindings - data.findings.length} more findings in the full report
          </span>
          <button
            type="button"
            onClick={() => setRun((r) => r + 1)}
            className="rounded px-1.5 py-0.5 text-[0.6875rem] font-medium text-muted transition-colors hover:bg-surface-2 hover:text-ink"
          >
            Replay
          </button>
        </div>
      </div>
    </div>
  );
}
