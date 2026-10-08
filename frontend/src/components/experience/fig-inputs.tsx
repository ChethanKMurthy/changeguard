"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";

import { cn } from "@/lib/cn";
import type { InputsFigure } from "@/lib/experience-data";

import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;

type Row = { path: string; base: boolean; head: boolean; op: "M" | "A" | "D" | "R" | null; additions: number; deletions: number };

const OP_STYLE = {
  M: "border-signal/50 bg-signal-tint text-signal",
  A: "border-ok/40 bg-ok-tint text-ok",
  D: "border-danger/40 bg-danger-tint text-danger",
  R: "border-line-strong bg-surface-2 text-ink-soft",
} as const;

const OP_LABEL = { M: "modified", A: "added", D: "deleted", R: "renamed" } as const;

function Presence({ present, op, delay, play }: { present: boolean; op: Row["op"]; delay: number; play: boolean }) {
  return (
    <motion.span
      className={cn(
        "inline-flex size-[18px] items-center justify-center rounded-[5px] border",
        present ? (op && op !== "D" ? OP_STYLE[op] : "border-ink bg-ink") : "border-dashed border-line-strong",
      )}
      initial={play ? { opacity: 0, scale: 0.6 } : false}
      animate={play ? { opacity: 1, scale: 1 } : undefined}
      transition={{ duration: 0.3, delay, ease: EASE }}
      aria-hidden="true"
    >
      {present && !op && <span className="size-1.5 rounded-[2px] bg-bg" />}
      {present && op && op !== "D" && <span className="font-mono text-[0.5625rem] font-bold">{op}</span>}
    </motion.span>
  );
}

/** Fig. 2: the snapshot, the patch, and the head revision rebuilt from them, file by file. */
export function FigInputs({ data }: { data: InputsFigure }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const animate = !reduce;
  const play = animate && inView;

  const changed = new Map(data.changed.map((c) => [c.path, c]));
  const paths = Array.from(new Set([...data.baseFiles, ...data.changed.map((c) => c.path)])).sort();
  const rows: Row[] = paths.map((path) => {
    const c = changed.get(path);
    const op = c ? ({ modified: "M", added: "A", deleted: "D", renamed: "R", copied: "A" } as const)[c.status] : null;
    return {
      path,
      base: data.baseFiles.includes(path),
      head: op !== "D",
      op,
      additions: c?.additions ?? 0,
      deletions: c?.deletions ?? 0,
    };
  });
  const headCount = rows.filter((r) => r.head).length;
  const col = (i: number, column: number) => (animate ? 0.1 + column * 0.45 + i * 0.05 : 0);

  return (
    <Plate label="workspace · in memory" meta={`${data.baseFiles.length} → ${headCount} files`}>
      <div ref={ref} className="relative overflow-x-auto scrollbar-thin">
        <table className="w-full min-w-[520px] border-collapse text-[0.8125rem]">
          <caption className="sr-only">
            Files in the snapshot (base revision), the operation the patch applies, and the files in the rebuilt head revision.
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-[0.6875rem] text-muted">
              <th scope="col" className="px-4 py-2 font-medium">File</th>
              <th scope="col" className="w-[92px] px-2 py-2 text-center font-medium">Snapshot</th>
              <th scope="col" className="w-[132px] px-2 py-2 font-medium">Patch</th>
              <th scope="col" className="w-[92px] px-2 py-2 text-center font-medium">Head</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={row.path} className={cn("border-b border-line last:border-b-0", row.op && "bg-surface/60")}>
                <th scope="row" className="px-4 py-2 text-left font-normal">
                  <span className={cn("font-mono text-[0.75rem]", row.op ? "text-ink" : "text-muted")}>{row.path}</span>
                </th>
                <td className="px-2 py-2 text-center">
                  <Presence present={row.base} op={null} delay={col(i, 0)} play={play} />
                  <span className="sr-only">{row.base ? "present" : "absent"}</span>
                </td>
                <td className="px-2 py-2">
                  {row.op ? (
                    <motion.span
                      className="inline-flex items-center gap-2"
                      initial={play ? { opacity: 0, x: -8 } : false}
                      animate={play ? { opacity: 1, x: 0 } : undefined}
                      transition={{ duration: 0.35, delay: col(i, 1), ease: EASE }}
                    >
                      <span className={cn("rounded-[4px] border px-1.5 text-[0.6875rem] font-medium", OP_STYLE[row.op])}>{OP_LABEL[row.op]}</span>
                      <span className="font-mono text-[0.6875rem] numeric">
                        <span className="text-ok">+{row.additions}</span> <span className="text-danger">−{row.deletions}</span>
                      </span>
                    </motion.span>
                  ) : (
                    <span className="text-[0.6875rem] text-faint">unchanged</span>
                  )}
                </td>
                <td className="px-2 py-2 text-center">
                  <Presence present={row.head} op={row.op} delay={col(i, 2)} play={play} />
                  <span className="sr-only">{row.head ? (row.op ? OP_LABEL[row.op] : "present") : "absent"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-line bg-surface px-4 py-2.5 text-[0.75rem] text-muted">
        <span>Patch applied in memory: no checkout, no extraction to disk</span>
        <span>No repository script, hook, or test runs</span>
      </div>
    </Plate>
  );
}
