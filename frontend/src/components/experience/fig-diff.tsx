"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useMemo, useState } from "react";

import type { FileSummary, Finding } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { CATEGORY_LABEL, SEVERITY_LABEL, SEVERITY_ORDER } from "@/lib/format";
import { renderInlineCode } from "@/lib/inline-code";

import { DiffViewer } from "../code/diff-viewer";
import { ProvenanceGlyph, SeverityMark } from "../ui/badges";
import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * Fig. 3: the whole patch, first without and then with ChangeGuard's markers.
 * Readers can form their own view before the analysis is revealed.
 */
export function FigDiff({ files: input, findings }: { files: FileSummary[]; findings: Finding[] }) {
  const reduce = useReducedMotion();
  const files = useMemo(() => {
    const count = (path: string) => findings.filter((f) => f.location.file === path).length;
    return [...input].sort((a, b) => count(b.path) - count(a.path) || a.path.localeCompare(b.path));
  }, [input, findings]);
  const [revealed, setRevealed] = useState(false);
  const [active, setActive] = useState(files[0]?.path ?? "");
  const [selected, setSelected] = useState<string | null>(null);
  const file = files.find((f) => f.path === active) ?? files[0];
  const byFile = useMemo(() => {
    const map = new Map<string, Finding[]>();
    for (const f of findings) map.set(f.location.file, [...(map.get(f.location.file) ?? []), f]);
    for (const list of map.values()) list.sort((a, b) => (a.location.start_line ?? 0) - (b.location.start_line ?? 0));
    return map;
  }, [findings]);
  const fileFindings = byFile.get(file?.path ?? "") ?? [];

  if (!file) return null;
  return (
    <Plate
      label={
        <span className="flex flex-wrap items-center gap-1" role="group" aria-label="Changed files">
          {files.map((f) => {
            const count = byFile.get(f.path)?.length ?? 0;
            const isActive = f.path === file.path;
            return (
              <button
                key={f.path}
                type="button"
                aria-pressed={isActive}
                onClick={() => {
                  setActive(f.path);
                  setSelected(null);
                }}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded-md px-2 font-mono text-[0.6875rem] transition-colors duration-150",
                  isActive ? "bg-surface-2 text-ink" : "text-muted hover:text-ink",
                )}
              >
                {f.path.split("/").pop()}
                {revealed && count > 0 && (
                  <span className="rounded-full bg-signal-tint-strong px-1.5 text-[0.625rem] font-semibold text-signal numeric">{count}</span>
                )}
              </button>
            );
          })}
        </span>
      }
      meta={
        <button
          type="button"
          aria-pressed={revealed}
          onClick={() => {
            setRevealed((r) => !r);
            setSelected(null);
          }}
          className={cn(
            "inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 font-sans text-[0.75rem] font-medium transition-colors duration-150",
            revealed ? "border-signal/50 bg-signal-tint text-signal" : "border-line-strong bg-bg text-ink hover:bg-surface",
          )}
        >
          <span aria-hidden="true">{revealed ? "◆" : "◇"}</span>
          {revealed ? `Showing ${findings.length} findings` : "Show what ChangeGuard flagged"}
        </button>
      }
    >
      <DiffViewer
        file={file}
        findings={revealed ? findings : []}
        selectedId={selected ?? undefined}
        onSelect={(id) => setSelected(id)}
        className="rounded-none border-0"
        maxHeight={460}
      />
      <AnimatePresence initial={false}>
        {revealed && (
          <motion.div
            key="findings"
            initial={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, height: "auto" }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: EASE }}
            className="overflow-hidden border-t border-line bg-surface"
          >
            {fileFindings.length === 0 ? (
              <p className="px-4 py-3 text-[0.8125rem] text-muted">No findings point into this file.</p>
            ) : (
              <ul className="divide-y divide-line">
                {[...fileFindings]
                  .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
                  .map((f) => (
                    <li key={f.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelected(f.id);
                          if (f.location.start_line && f.location.side === "head") {
                            document.getElementById(`L${f.location.start_line}`)?.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
                          }
                        }}
                        className={cn(
                          "grid w-full grid-cols-[16px_minmax(0,1fr)_auto] items-start gap-3 px-4 py-2.5 text-left transition-colors duration-150",
                          selected === f.id ? "bg-signal-tint" : "hover:bg-surface-2",
                        )}
                        aria-pressed={selected === f.id}
                      >
                        <ProvenanceGlyph kind={f.kind} className="mt-px text-center text-[0.75rem]" />
                        <span className="min-w-0">
                          <span className="block text-[0.8125rem] font-medium text-ink">{renderInlineCode(f.title)}</span>
                          <span className="mt-0.5 block font-mono text-[0.625rem] text-faint">
                            line {f.location.start_line ?? "—"} · {f.rule_id} · {CATEGORY_LABEL[f.category]}
                          </span>
                        </span>
                        <span className="mt-0.5 flex items-center gap-1.5 text-[0.6875rem] text-muted">
                          <SeverityMark severity={f.severity} />
                          {SEVERITY_LABEL[f.severity]}
                        </span>
                      </button>
                    </li>
                  ))}
              </ul>
            )}
            <p className="border-t border-line px-4 py-2 text-[0.75rem] text-muted">
              Each finding has evidence behind it.{" "}
              <Link
                href={selected ? `/reports/sample#${selected}` : "/reports/sample"}
                className="text-ink underline decoration-line-strong underline-offset-2 hover:decoration-signal"
              >
                {selected ? "Read the selected finding in the report" : "Read them in the recorded report"}
              </Link>
              .
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </Plate>
  );
}
