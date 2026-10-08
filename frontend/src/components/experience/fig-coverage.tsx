"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";

import { cn } from "@/lib/cn";
import type { CoverageFigure } from "@/lib/experience-data";

import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;

/** Fig. 8: static test mapping per changed symbol, and measured coverage of each changed executable line. */
export function FigCoverage({ data }: { data: CoverageFigure }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.3 });
  const play = !reduce && inView;
  const withTests = data.symbols.filter((s) => s.tests > 0).length;
  let cell = 0;

  return (
    <Plate label={`test mapping + coverage · ${data.format ?? "no report"}`} meta={`${withTests}/${data.symbols.length} symbols tested · ${data.covered}/${data.executable} lines ran`}>
      <div ref={ref} className="grid lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        {/* Test mapping */}
        <div className="border-b border-line p-4 sm:p-5 lg:border-b-0 lg:border-r">
          <h3 className="text-[0.8125rem] font-semibold text-ink">Tests that import and reference each symbol</h3>
          <p className="mt-0.5 text-[0.75rem] text-muted">Static: found by reading test files, not by running them.</p>
          <ul className="mt-4 space-y-2.5">
            {data.symbols.map((s, i) => (
              <motion.li
                key={`${s.file}:${s.qualname}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3"
                initial={play ? { opacity: 0, x: -6 } : false}
                animate={play ? { opacity: 1, x: 0 } : undefined}
                transition={{ duration: 0.35, delay: i * 0.07, ease: EASE }}
              >
                <span className="min-w-0">
                  <span className="block truncate font-mono text-[0.75rem] text-ink">{s.qualname}</span>
                  <span className="block font-mono text-[0.625rem] text-faint">{s.change}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  {s.tests > 0 ? (
                    <>
                      <span className="flex gap-1" aria-hidden="true">
                        {Array.from({ length: s.tests }, (_, k) => (
                          <span key={k} className="h-3.5 w-2 rounded-[2px] bg-ok" />
                        ))}
                      </span>
                      <span className="text-[0.6875rem] text-muted numeric">
                        {s.tests} test{s.tests > 1 ? "s" : ""}
                      </span>
                    </>
                  ) : (
                    <span className="rounded-[4px] border border-signal/45 bg-signal-tint px-1.5 text-[0.6875rem] font-medium text-signal">no test</span>
                  )}
                </span>
              </motion.li>
            ))}
          </ul>
        </div>

        {/* Patch coverage */}
        <div className="p-4 sm:p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h3 className="text-[0.8125rem] font-semibold text-ink">Changed executable lines the test suite ran</h3>
            <span className="text-[0.75rem] text-muted">
              <span className="text-2xl font-[650] tracking-[-0.03em] text-ink numeric [font-stretch:112%]">{data.percent ?? "—"}%</span> patch
              coverage
            </span>
          </div>
          <div className="mt-4 space-y-4">
            {data.files.map((file) => (
              <div key={file.path}>
                <p className="mb-1.5 flex items-baseline justify-between gap-3 font-mono text-[0.6875rem]">
                  <span className="truncate text-ink-soft">{file.path}</span>
                  <span className="shrink-0 text-faint numeric">
                    {file.covered}/{file.executable}
                  </span>
                </p>
                <ul className="flex flex-wrap gap-1" aria-label={`${file.path}: ${file.covered} of ${file.executable} changed executable lines ran`}>
                  {Array.from({ length: file.covered }, (_, k) => {
                    const delay = (cell++) * 0.03;
                    return (
                      <motion.li
                        key={`c${k}`}
                        className="flex h-7 w-10 items-center justify-center rounded-[4px] border border-ok/35 bg-ok-tint"
                        title="Executed by the test suite"
                        initial={play ? { opacity: 0, scale: 0.7 } : false}
                        animate={play ? { opacity: 1, scale: 1 } : undefined}
                        transition={{ duration: 0.25, delay: 0.3 + delay, ease: EASE }}
                      >
                        <span className="size-1.5 rounded-full bg-ok" aria-hidden="true" />
                        <span className="sr-only">ran</span>
                      </motion.li>
                    );
                  })}
                  {file.uncovered.map((line) => {
                    const delay = (cell++) * 0.03;
                    return (
                      <motion.li
                        key={line}
                        className="flex h-7 w-10 items-center justify-center rounded-[4px] border border-danger/40 bg-danger-tint font-mono text-[0.625rem] font-medium text-danger numeric"
                        title={`Line ${line}: never executed`}
                        initial={play ? { opacity: 0, scale: 0.7 } : false}
                        animate={play ? { opacity: 1, scale: 1 } : undefined}
                        transition={{ duration: 0.25, delay: 0.3 + delay, ease: EASE }}
                      >
                        L{line}
                        <span className="sr-only"> never ran</span>
                      </motion.li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
          <div className="mt-5 flex flex-wrap gap-x-5 gap-y-1.5 text-[0.75rem] text-muted">
            <span className="flex items-center gap-1.5">
              <span className="inline-flex h-4 w-6 items-center justify-center rounded-[3px] border border-ok/35 bg-ok-tint" aria-hidden="true">
                <span className="size-1 rounded-full bg-ok" />
              </span>
              ran
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-flex h-4 w-6 items-center justify-center rounded-[3px] border border-danger/40 bg-danger-tint font-mono text-[0.5rem] text-danger" aria-hidden="true">
                L
              </span>
              never ran
            </span>
            <span className={cn(data.staleFiles.length ? "text-signal" : undefined)}>
              {data.staleFiles.length ? `Report looks stale for ${data.staleFiles.length} file(s)` : "Staleness check passed"}
            </span>
          </div>
        </div>
      </div>
    </Plate>
  );
}
