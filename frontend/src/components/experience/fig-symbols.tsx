"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";

import type { SymbolChangeSummary } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { diffParams, parseSignature } from "@/lib/signature";

import { Plate } from "./plate";

const EASE = [0.22, 1, 0.36, 1] as const;

function verdict(s: SymbolChangeSummary): { label: string; tone: string } {
  if (s.change === "added") return { label: "New", tone: "border-ok/40 bg-ok-tint text-ok" };
  if (s.change === "removed") return { label: "Removed", tone: "border-danger/40 bg-danger-tint text-danger" };
  if (s.breaking) return { label: "Breaking", tone: "border-danger/40 bg-danger-tint text-danger" };
  if (s.signature_before !== s.signature_after) return { label: "Compatible", tone: "border-line-strong bg-surface text-ink-soft" };
  return { label: "Body only", tone: "border-line bg-bg text-muted" };
}

function Signature({ symbol }: { symbol: SymbolChangeSummary }) {
  const changed = symbol.change === "modified" && symbol.signature_before !== symbol.signature_after;
  if (!changed) {
    const sig = symbol.signature_after ?? symbol.signature_before ?? "";
    return <code className="block font-mono text-[0.72rem] text-muted [overflow-wrap:anywhere]">{sig}</code>;
  }
  const params = diffParams(symbol.signature_before ?? null, symbol.signature_after ?? null);
  const name = parseSignature(symbol.signature_after ?? "")?.prefix ?? symbol.qualname;
  return (
    <div className="font-mono text-[0.72rem] leading-[1.9]">
      <span className="text-ink">{name}(</span>
      {params.map((p, i) => (
        <span key={`${p.name}-${p.state}`}>
          <span
            className={cn(
              "whitespace-nowrap rounded-[3px] px-1 py-px",
              p.state === "removed" && "bg-diff-del text-danger line-through decoration-danger/60",
              p.state === "added" && (p.optional ? "bg-diff-add text-ok" : "bg-diff-add text-ok ring-1 ring-ok/40"),
              p.state === "changed" && "bg-highlight text-ink",
              p.state === "kept" && "text-ink-soft",
            )}
            title={
              p.state === "removed"
                ? "parameter removed"
                : p.state === "added"
                  ? p.optional
                    ? "parameter added, with a default"
                    : "required parameter added"
                  : p.state === "changed"
                    ? "parameter changed"
                    : undefined
            }
          >
            {p.text}
          </span>
          {i < params.length - 1 && <span className="text-faint">,</span>}{" "}
        </span>
      ))}
      <span className="text-ink">)</span>
    </div>
  );
}

/** Fig. 4: every changed symbol, with a parameter-level view of signature changes. */
export function FigSymbols({ symbols }: { symbols: SymbolChangeSummary[] }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLUListElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.3 });
  const play = !reduce && inView;
  const rows = symbols.filter((s) => s.kind !== "test");

  return (
    <Plate label="structural diff · tree-sitter" meta={`${rows.length} changed symbols`}>
      <div className="hidden grid-cols-[minmax(150px,0.7fr)_minmax(0,2fr)_88px_96px] gap-4 border-b border-line px-4 py-2 text-[0.6875rem] font-medium text-muted md:grid">
        <span>Symbol</span>
        <span>Signature (removed · added)</span>
        <span className="text-right">Complexity</span>
        <span className="text-right">Verdict</span>
      </div>
      <ul ref={ref} className="divide-y divide-line">
        {rows.map((s, i) => {
          const v = verdict(s);
          return (
            <motion.li
              key={`${s.file}:${s.qualname}`}
              initial={play ? { opacity: 0, y: 8 } : false}
              animate={play ? { opacity: 1, y: 0 } : undefined}
              transition={{ duration: 0.4, delay: i * 0.08, ease: EASE }}
              className={cn(
                "grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-2 px-4 py-3 md:grid-cols-[minmax(150px,0.7fr)_minmax(0,2fr)_88px_96px] md:items-center",
                s.breaking && "bg-danger-tint/40",
              )}
            >
              <div className="min-w-0">
                <span className="block truncate font-mono text-[0.78rem] font-medium text-ink">{s.qualname}</span>
                <span className="block truncate font-mono text-[0.625rem] text-faint">
                  {s.file.split("/").pop()}:{s.start_line} · {s.change}
                </span>
              </div>
              <span className={cn("h-6 self-start justify-self-end rounded-[5px] border px-2 text-[0.6875rem] font-semibold leading-[22px] md:order-last", v.tone)}>
                {v.label}
              </span>
              <div className="col-span-2 min-w-0 md:col-span-1">
                <Signature symbol={s} />
              </div>
              <span className="col-span-2 font-mono text-[0.72rem] text-muted numeric md:col-span-1 md:text-right">
                <span className="md:hidden">complexity </span>
                {s.complexity_before ?? "—"} → <span className={cn((s.complexity_after ?? 0) > (s.complexity_before ?? 0) && "text-signal")}>{s.complexity_after ?? "—"}</span>
              </span>
            </motion.li>
          );
        })}
      </ul>
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 border-t border-line bg-surface px-4 py-2.5 text-[0.75rem] text-muted">
        <span className="flex items-center gap-1.5">
          <span className="rounded-[3px] bg-diff-del px-1 font-mono text-[0.625rem] text-danger line-through">param</span> removed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="rounded-[3px] bg-diff-add px-1 font-mono text-[0.625rem] text-ok ring-1 ring-ok/40">param</span> required, added
        </span>
        <span className="flex items-center gap-1.5">
          <span className="rounded-[3px] bg-diff-add px-1 font-mono text-[0.625rem] text-ok">param = …</span> added with a default
        </span>
        <span>Verdict is the engine&rsquo;s, from the structural diff.</span>
      </div>
    </Plate>
  );
}
