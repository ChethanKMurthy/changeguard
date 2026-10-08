"use client";

import { motion, useReducedMotion } from "motion/react";

import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { StageStatus, StageView } from "@/lib/stages";

const EASE = [0.22, 1, 0.36, 1] as const;

export function StageIndicator({ status, className }: { status: StageStatus; className?: string }) {
  return (
    <span
      className={cn(
        "relative flex size-[18px] shrink-0 items-center justify-center rounded-[5px] border transition-colors duration-200",
        status === "pending" && "border-line-strong bg-bg",
        status === "running" && "border-signal bg-signal-tint",
        status === "ok" && "border-ink bg-ink text-bg",
        status === "skipped" && "border-dashed border-line-strong bg-bg",
        status === "warning" && "border-signal bg-signal text-white dark:text-bg",
        status === "failed" && "border-danger bg-danger text-white dark:text-bg",
        className,
      )}
      aria-hidden="true"
    >
      {status === "running" && <span className="animate-indicator size-2 rounded-[2px] bg-signal" />}
      {status === "ok" && (
        <svg viewBox="0 0 12 12" className="size-2.5">
          <path d="M2.5 6.2 5 8.6 9.6 3.6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      {status === "warning" && <span className="font-mono text-[0.625rem] font-bold leading-none">!</span>}
      {status === "failed" && <span className="font-mono text-[0.625rem] font-bold leading-none">×</span>}
      {status === "skipped" && <span className="h-px w-2 bg-faint" />}
    </span>
  );
}

const STATUS_WORD: Record<StageStatus, string> = {
  pending: "Waiting",
  running: "Running",
  ok: "Done",
  skipped: "Skipped",
  warning: "Done with warnings",
  failed: "Failed",
};

/**
 * Vertical lab log of the analysis pipeline. The amber trace on the left fills
 * as stages complete: it represents the change moving through the instrument.
 */
export function PipelineTrack({ stages, className, dense }: { stages: StageView[]; className?: string; dense?: boolean }) {
  const reduce = useReducedMotion();
  const done = stages.filter((s) => s.status !== "pending" && s.status !== "running").length;
  const runningIndex = stages.findIndex((s) => s.status === "running");
  const progress = stages.length > 1 ? Math.max(done - 1, runningIndex, 0) / (stages.length - 1) : 0;

  return (
    <ol className={cn("relative", className)} aria-label="Analysis pipeline">
      <span className="absolute bottom-3 left-[8.5px] top-3 w-px bg-line" aria-hidden="true" />
      <motion.span
        className="absolute left-[8px] top-3 w-[2px] origin-top rounded-full bg-signal-glow"
        style={{ height: "calc(100% - 1.5rem)" }}
        initial={false}
        animate={{ scaleY: progress }}
        transition={{ duration: reduce ? 0 : 0.45, ease: EASE }}
        aria-hidden="true"
      />
      {stages.map((stage) => (
        <li key={stage.name} className={cn("relative flex gap-3.5", dense ? "py-1.5" : "py-2.5")}>
          <StageIndicator status={stage.status} className="z-10 mt-[3px]" />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-3">
              <span
                className={cn(
                  "text-sm transition-colors duration-200",
                  stage.status === "pending" ? "text-faint" : "font-medium text-ink",
                )}
              >
                {stage.label}
                <span className="sr-only">: {STATUS_WORD[stage.status]}</span>
              </span>
              <span className="shrink-0 font-mono text-[0.6875rem] text-muted numeric">
                {stage.status === "running" ? "…" : stage.status === "skipped" ? "—" : stage.durationMs !== undefined && stage.status !== "pending" ? formatDuration(stage.durationMs) : ""}
              </span>
            </div>
            {!dense && stage.detail && (
              <motion.p
                key={stage.detail}
                initial={reduce ? false : { opacity: 0, y: -2 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, ease: EASE }}
                className={cn("mt-0.5 text-[0.8125rem] leading-snug", stage.status === "skipped" ? "text-faint" : "text-muted")}
              >
                {stage.detail}
              </motion.p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
