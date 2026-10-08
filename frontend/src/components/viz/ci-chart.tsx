"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";

export interface CIRow {
  key: string;
  label: string;
  sublabel?: string;
  value: number | null;
  low?: number | null;
  high?: number | null;
  emphasis?: boolean;
  tone?: "ink" | "signal" | "ai" | "muted";
}

const TONE: Record<NonNullable<CIRow["tone"]>, { dot: string; bar: string }> = {
  ink: { dot: "bg-ink", bar: "bg-ink/35" },
  signal: { dot: "bg-signal", bar: "bg-signal/40" },
  ai: { dot: "bg-ai", bar: "bg-ai/40" },
  muted: { dot: "bg-faint", bar: "bg-faint/40" },
};

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * Dot-and-whisker chart: a point estimate with its 95% bootstrap interval.
 * Rendered in HTML so it stays crisp and responsive; draws once when scrolled into view.
 */
export function CIChart({
  rows,
  title,
  className,
  interval = "95% CI",
}: {
  rows: CIRow[];
  title: string;
  className?: string;
  /** Label for the whiskers; null for point estimates without intervals. */
  interval?: string | null;
}) {
  const reduce = useReducedMotion();
  return (
    <div className={cn("min-w-0", className)}>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h4 className="text-[0.8125rem] font-semibold text-ink">{title}</h4>
        {interval && <span className="font-mono text-[0.625rem] text-faint">{interval}</span>}
      </div>
      <div className="relative">
        <div className="pointer-events-none absolute inset-0 grid grid-cols-4" aria-hidden="true">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className="border-l border-dashed border-line first:border-l-line-strong" />
          ))}
          <span className="absolute inset-y-0 right-0 border-r border-dashed border-line" />
        </div>
        <ul className="relative space-y-3.5 py-1">
          {rows.map((row, index) => {
            const tone = TONE[row.tone ?? "ink"];
            const value = row.value ?? 0;
            const low = row.low ?? value;
            const high = row.high ?? value;
            return (
              <li
                key={row.key}
                className="grid gap-1"
                aria-label={`${row.label}: ${
                  row.value == null
                    ? "no data"
                    : `${(value * 100).toFixed(1)}%${row.low != null && row.high != null ? `, 95% interval ${(low * 100).toFixed(0)} to ${(high * 100).toFixed(0)}%` : ""}`
                }`}
              >
                <div className="flex items-baseline justify-between gap-3 text-xs">
                  <span className={cn("truncate", row.emphasis ? "font-semibold text-ink" : "text-ink-soft")}>{row.label}</span>
                  <span className={cn("font-mono numeric", row.emphasis ? "text-ink" : "text-muted")}>
                    {row.value == null ? "—" : `${(value * 100).toFixed(1)}%`}
                  </span>
                </div>
                <div className="relative h-3">
                  {row.value != null && (
                    <>
                      <motion.span
                        className={cn("absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full", tone.bar)}
                        style={{ left: `${low * 100}%`, width: `${Math.max(0.6, (high - low) * 100)}%`, originX: 0 }}
                        initial={reduce ? false : { scaleX: 0, opacity: 0 }}
                        whileInView={{ scaleX: 1, opacity: 1 }}
                        viewport={{ once: true, margin: "-40px" }}
                        transition={{ duration: 0.6, delay: index * 0.06, ease: EASE }}
                      />
                      <motion.span
                        className={cn("absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-bg", tone.dot)}
                        style={{ left: `${value * 100}%` }}
                        initial={reduce ? false : { scale: 0 }}
                        whileInView={{ scale: 1 }}
                        viewport={{ once: true, margin: "-40px" }}
                        transition={{ duration: 0.35, delay: 0.25 + index * 0.06, ease: EASE }}
                      />
                    </>
                  )}
                </div>
                {row.sublabel && <span className="text-[0.6875rem] text-faint">{row.sublabel}</span>}
              </li>
            );
          })}
        </ul>
        <div className="mt-2 flex justify-between font-mono text-[0.625rem] text-faint" aria-hidden="true">
          <span>0%</span>
          <span>25%</span>
          <span>50%</span>
          <span>75%</span>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
}
