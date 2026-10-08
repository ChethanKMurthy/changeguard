"use client";

import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { useRef, useState } from "react";

import type { Evidence } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import type { CallersFigure } from "@/lib/experience-data";
import { renderInlineCode } from "@/lib/inline-code";

import { EvidenceCard } from "../report/evidence";
import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;
const ROW = 58;
const EDGE_W = 84;

type Site = { evidence: Evidence | null };

function callOf(e: Evidence): string {
  return typeof e.data.call === "string" ? e.data.call : "";
}

function problemsOf(e: Evidence): string[] {
  return Array.isArray(e.data.problems) ? e.data.problems.map(String) : [];
}

function Fan({
  symbol,
  sites,
  selected,
  onSelect,
  play,
  delay,
}: {
  symbol: CallersFigure["symbols"][number];
  sites: Site[];
  selected: string | null;
  onSelect: (id: string) => void;
  play: boolean;
  delay: number;
}) {
  const height = Math.max(sites.length, 1) * ROW;
  const mid = height / 2;
  return (
    <div className="p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-[0.75rem] font-semibold text-ink">{symbol.qualname}</span>
        <span className="text-[0.6875rem] text-muted">
          {symbol.callSites} call sites in {symbol.callSiteFiles} files ·{" "}
          <span className={cn("font-semibold", symbol.incompatible ? "text-danger" : "text-ok")}>
            {symbol.incompatible ? `${symbol.incompatible} incompatible` : "all bind"}
          </span>
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-[minmax(96px,160px)_minmax(32px,96px)_minmax(0,1fr)]" style={{ minHeight: height }}>
        {/* Hub (the panel header names the symbol on small screens) */}
        <div className="hidden items-center sm:flex">
          <motion.div
            initial={play ? { opacity: 0, x: -6 } : false}
            animate={play ? { opacity: 1, x: 0 } : undefined}
            transition={{ duration: 0.35, delay, ease: EASE }}
            className={cn(
              "w-full rounded-[8px] border px-2.5 py-2",
              symbol.breaking ? "border-danger/45 bg-danger-tint" : "border-line-strong bg-surface",
            )}
          >
            <span className="block truncate font-mono text-[0.6875rem] font-semibold text-ink">{symbol.qualname}</span>
            <span className={cn("block text-[0.625rem]", symbol.breaking ? "text-danger" : "text-muted")}>
              {symbol.breaking ? "breaking signature" : "compatible signature"}
            </span>
          </motion.div>
        </div>
        {/* Edges */}
        <svg viewBox={`0 0 ${EDGE_W} ${height}`} preserveAspectRatio="none" className="hidden h-full w-full sm:block" style={{ height }} aria-hidden="true">
          {sites.map((site, i) => {
            const y = i * ROW + ROW / 2;
            const bad = Boolean(site.evidence);
            return (
              <motion.path
                key={i}
                d={`M0 ${mid} C ${EDGE_W * 0.55} ${mid}, ${EDGE_W * 0.45} ${y}, ${EDGE_W} ${y}`}
                fill="none"
                vectorEffect="non-scaling-stroke"
                className={bad ? "stroke-danger" : "stroke-line-strong"}
                strokeWidth={bad ? 1.6 : 1.2}
                strokeDasharray={bad ? undefined : "3 3"}
                initial={play ? { pathLength: 0, opacity: 0 } : false}
                animate={play ? { pathLength: 1, opacity: 1 } : undefined}
                transition={{ duration: 0.5, delay: delay + 0.2 + i * 0.12, ease: EASE }}
              />
            );
          })}
        </svg>
        {/* Call sites */}
        <ul className="min-w-0">
          {sites.map((site, i) => {
            const e = site.evidence;
            return (
              <motion.li
                key={i}
                style={{ height: ROW }}
                className="flex items-center"
                initial={play ? { opacity: 0 } : false}
                animate={play ? { opacity: 1 } : undefined}
                transition={{ duration: 0.3, delay: delay + 0.45 + i * 0.12 }}
              >
                {e ? (
                  <button
                    type="button"
                    onClick={() => onSelect(e.id)}
                    aria-pressed={selected === e.id}
                    className={cn(
                      "flex w-full min-w-0 items-start gap-2 rounded-[8px] border px-2.5 py-1.5 text-left transition-colors duration-150",
                      selected === e.id ? "border-danger/60 bg-danger-tint" : "border-transparent hover:border-line hover:bg-surface",
                    )}
                  >
                    <span className="mt-[5px] size-2 shrink-0 rounded-full bg-danger" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block truncate font-mono text-[0.6875rem] text-ink">
                        {e.file}:{e.start_line}
                      </span>
                      <span className="block truncate text-[0.6875rem] text-danger">{renderInlineCode(problemsOf(e)[0] ?? "incompatible")}</span>
                    </span>
                  </button>
                ) : (
                  <span className="flex min-w-0 items-start gap-2 px-2.5 py-1.5">
                    <span className="mt-[5px] size-2 shrink-0 rounded-full border border-ok bg-bg" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block text-[0.6875rem] text-ink-soft">Compatible call</span>
                      <span className="block truncate text-[0.6875rem] text-muted">binds the new signature</span>
                    </span>
                  </span>
                )}
              </motion.li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

/** Fig. 5: call sites of each changed signature, replayed against the new parameter list. */
export function FigCallers({ data }: { data: CallersFigure }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.3 });
  const play = !reduce && inView;
  const [selected, setSelected] = useState<string | null>(data.incompatible[0]?.id ?? null);
  const ordered = [...data.symbols].sort((a, b) => Number(b.breaking) - Number(a.breaking));
  const chosen = data.incompatible.find((e) => e.id === selected) ?? null;

  return (
    <Plate label="cross-file references · argument binding" meta={`${data.checked} call sites checked · ${data.incompatibleTotal} incompatible`}>
      <div ref={ref} className="divide-y divide-line">
        {ordered.map((symbol, k) => {
          const leaf = symbol.qualname.split(".").pop() ?? symbol.qualname;
          const bad = data.incompatible.filter((e) => new RegExp(`(^|[^\\w])${leaf}\\(`).test(callOf(e)));
          const compatible = Math.max(symbol.callSites - bad.length, 0);
          const sites: Site[] = [...bad.map((e) => ({ evidence: e })), ...Array.from({ length: compatible }, () => ({ evidence: null }))];
          return (
            <Fan key={symbol.qualname} symbol={symbol} sites={sites} selected={selected} onSelect={setSelected} play={play} delay={k * 0.35} />
          );
        })}
      </div>
      <div className="border-t border-line bg-surface p-4 sm:p-5">
        <AnimatePresence mode="wait" initial={false}>
          {chosen ? (
            <motion.div
              key={chosen.id}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22, ease: EASE }}
            >
              <EvidenceCard evidence={chosen} />
            </motion.div>
          ) : (
            <p className="text-[0.8125rem] text-muted">Select an incompatible call site to see its evidence.</p>
          )}
        </AnimatePresence>
        <p className="mt-3 text-[0.75rem] leading-relaxed text-muted">
          Incompatible call sites are kept as evidence with their exact location. Compatible ones are counted but not stored.
        </p>
      </div>
    </Plate>
  );
}
