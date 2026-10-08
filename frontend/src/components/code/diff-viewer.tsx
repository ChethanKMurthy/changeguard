"use client";

import { useMemo } from "react";

import type { FileSummary, Finding, HunkModel } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { languageForPath, SEVERITY_ORDER } from "@/lib/format";
import type { TokenLine } from "@/lib/highlight";

import { SeverityMark } from "../ui/badges";
import { TokenText, useTokens } from "./code";

type Annotation = { finding: Finding; side: "head" | "base" };

function useHunkTokens(hunk: HunkModel, lang: string) {
  // Tokenize each side of the hunk as one block so multi-line constructs highlight correctly.
  const newSide = useMemo(() => hunk.lines.filter((l) => l.kind !== "del").map((l) => l.content).join("\n"), [hunk]);
  const oldSide = useMemo(() => hunk.lines.filter((l) => l.kind === "del").map((l) => l.content).join("\n"), [hunk]);
  const newTokens = useTokens(newSide, lang);
  const oldTokens = useTokens(oldSide, lang);
  return { newTokens, oldTokens };
}

function Hunk({
  hunk,
  lang,
  annotations,
  highlight,
  selectedId,
  onSelect,
}: {
  hunk: HunkModel;
  lang: string;
  annotations: Map<string, Annotation[]>;
  highlight: Set<number>;
  selectedId?: string;
  onSelect?: (id: string) => void;
}) {
  const { newTokens, oldTokens } = useHunkTokens(hunk, lang);
  let newIndex = 0;
  let oldIndex = 0;
  return (
    <tbody>
      <tr className="bg-surface-2/70">
        <td colSpan={4} className="px-3 py-1 font-mono text-[0.72rem] text-muted">
          <span className="text-faint">{hunk.header.split("@@").slice(0, 2).join("@@")}@@</span>
          {hunk.section && <span className="ml-2 text-ink-soft">{hunk.section}</span>}
        </td>
      </tr>
      {hunk.lines.map((line, i) => {
        let tokens: TokenLine | undefined;
        if (line.kind === "del") tokens = oldTokens?.[oldIndex++];
        else tokens = newTokens?.[newIndex++];
        const key = line.kind === "del" ? `base:${line.old}` : `head:${line.new}`;
        const notes = annotations.get(key) ?? [];
        const top = notes.length
          ? [...notes].sort((a, b) => SEVERITY_ORDER.indexOf(a.finding.severity) - SEVERITY_ORDER.indexOf(b.finding.severity))[0]
          : undefined;
        const selected = notes.some((n) => n.finding.id === selectedId);
        const hot = line.kind !== "del" && line.new != null && highlight.has(line.new);
        return (
          <tr
            key={i}
            id={line.new != null && line.kind !== "del" ? `L${line.new}` : undefined}
            className={cn(
              line.kind === "add" && "bg-diff-add",
              line.kind === "del" && "bg-diff-del",
              hot && "!bg-highlight",
              selected && "outline outline-1 -outline-offset-1 outline-signal",
            )}
          >
            <td className="w-[1%] select-none whitespace-nowrap px-2 text-right align-top text-faint numeric">{line.old ?? ""}</td>
            <td className="w-[1%] select-none whitespace-nowrap px-2 text-right align-top text-faint numeric">{line.new ?? ""}</td>
            <td className="w-6 select-none align-top">
              {top ? (
                <button
                  type="button"
                  onClick={() => onSelect?.(top.finding.id)}
                  className="flex h-[1.7em] w-6 items-center justify-center rounded-sm hover:bg-signal-tint-strong"
                  title={notes.map((n) => n.finding.title).join("\n")}
                  aria-label={`${notes.length} finding${notes.length > 1 ? "s" : ""} on this line: ${top.finding.title}`}
                >
                  <SeverityMark severity={top.finding.severity} className="size-2.5" />
                </button>
              ) : (
                <span
                  className={cn(
                    "flex h-[1.7em] w-6 items-center justify-center font-mono",
                    line.kind === "add" ? "text-ok" : line.kind === "del" ? "text-danger" : "text-transparent",
                  )}
                  aria-hidden="true"
                >
                  {line.kind === "add" ? "+" : line.kind === "del" ? "−" : " "}
                </span>
              )}
            </td>
            <td className="whitespace-pre pr-4 align-top">
              <TokenText tokens={tokens} fallback={line.content} />
            </td>
          </tr>
        );
      })}
    </tbody>
  );
}

/**
 * Unified diff of one file, with finding markers in the gutter.
 * Markers sit on the exact lines findings point at; clicking one selects the finding.
 */
export function DiffViewer({
  file,
  findings = [],
  highlightLines = [],
  selectedId,
  onSelect,
  className,
  maxHeight,
}: {
  file: FileSummary;
  findings?: Finding[];
  highlightLines?: number[];
  selectedId?: string;
  onSelect?: (id: string) => void;
  className?: string;
  maxHeight?: number;
}) {
  const lang = languageForPath(file.path);
  const annotations = useMemo(() => {
    const map = new Map<string, Annotation[]>();
    for (const finding of findings) {
      const loc = finding.location;
      if (loc.file !== file.path || !loc.start_line) continue;
      const end = Math.min(loc.end_line ?? loc.start_line, loc.start_line + 3);
      for (let ln = loc.start_line; ln <= end; ln++) {
        const key = `${loc.side}:${ln}`;
        map.set(key, [...(map.get(key) ?? []), { finding, side: loc.side }]);
      }
    }
    return map;
  }, [findings, file.path]);
  const highlight = useMemo(() => new Set(highlightLines), [highlightLines]);

  if (file.is_binary) {
    return <p className="rounded-md border border-line bg-surface p-4 text-sm text-muted">Binary file — content not analysed.</p>;
  }
  if (!file.hunks.length) {
    return (
      <p className="rounded-md border border-line bg-surface p-4 text-sm text-muted">
        {file.status === "renamed" ? `Renamed from ${file.old_path} without content changes.` : "No textual changes."}
      </p>
    );
  }
  return (
    <div
      className={cn("relative overflow-auto rounded-md border border-line bg-bg font-mono text-[0.78rem] leading-[1.7] scrollbar-thin", className)}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <table className="w-full min-w-max border-collapse">
        {file.hunks.map((hunk, i) => (
          <Hunk
            key={i}
            hunk={hunk}
            lang={lang}
            annotations={annotations}
            highlight={highlight}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ))}
      </table>
    </div>
  );
}
