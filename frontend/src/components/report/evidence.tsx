"use client";

import type { Evidence } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatLocation, languageForPath } from "@/lib/format";
import { renderInlineCode } from "@/lib/inline-code";

import { CodeExcerpt } from "../code/code";
import { EvidenceTag, Pill } from "../ui/badges";

const TYPE_LABEL: Record<Evidence["type"], string> = {
  diff_hunk: "Diff",
  code: "Code",
  call_site: "Call site",
  signature_change: "Signature change",
  static_diagnostic: "Static diagnostic",
  pattern_match: "Pattern match",
  test_reference: "Test reference",
  coverage: "Coverage",
  metric: "Metric",
  dependency: "Dependency",
  symbol_reference: "Reference",
};

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function SignatureDiff({ evidence }: { evidence: Evidence }) {
  const before = typeof evidence.data.before === "string" ? evidence.data.before : null;
  const after = typeof evidence.data.after === "string" ? evidence.data.after : null;
  const changes = asStrings(evidence.data.changes);
  return (
    <div className="space-y-3">
      <div className="relative overflow-x-auto rounded-md border border-line font-mono text-[0.78rem] leading-[1.75] scrollbar-thin">
        {before && (
          <div className="flex gap-3 bg-diff-del px-3 py-1">
            <span className="select-none text-danger" aria-label="Before">−</span>
            <span className="whitespace-pre">{before}</span>
          </div>
        )}
        {after && (
          <div className="flex gap-3 bg-diff-add px-3 py-1">
            <span className="select-none text-ok" aria-label="After">+</span>
            <span className="whitespace-pre">{after}</span>
          </div>
        )}
      </div>
      {changes.length > 0 && (
        <ul className="space-y-1 text-[0.8125rem] text-ink-soft">
          {changes.map((change) => (
            <li key={change} className="flex gap-2">
              <span className="mt-[0.55em] size-1 shrink-0 rounded-full bg-signal" aria-hidden="true" />
              <span>{renderInlineCode(change)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export { renderInlineCode };

function MiniDiff({ excerpt }: { excerpt: string }) {
  return (
    <div className="relative overflow-x-auto rounded-md border border-line font-mono text-[0.78rem] leading-[1.75] scrollbar-thin">
      {excerpt.split("\n").map((row, i) => {
        const add = row.startsWith("+");
        const del = row.startsWith("-");
        return (
          <div key={i} className={cn("flex gap-3 px-3", add && "bg-diff-add", del && "bg-diff-del")}>
            <span className={cn("select-none", add ? "text-ok" : del ? "text-danger" : "text-faint")}>{add ? "+" : del ? "−" : " "}</span>
            <span className="whitespace-pre">{add || del ? row.slice(1) : row}</span>
          </div>
        );
      })}
    </div>
  );
}

function CoverageStrip({ evidence }: { evidence: Evidence }) {
  const hits = (evidence.data.hits ?? {}) as Record<string, number>;
  const entries = Object.entries(hits).map(([line, count]) => [Number(line), Number(count)] as const);
  if (!entries.length) return null;
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1" role="list" aria-label="Changed executable lines and their hit counts">
        {entries.map(([line, count]) => (
          <span
            key={line}
            role="listitem"
            className={cn(
              "inline-flex h-6 min-w-9 items-center justify-center rounded-[4px] border px-1 font-mono text-[0.6875rem] numeric",
              count > 0 ? "border-ok/30 bg-ok-tint text-ok" : "border-danger/35 bg-danger-tint text-danger",
            )}
            title={`Line ${line}: ${count} hit${count === 1 ? "" : "s"}`}
          >
            L{line}
          </span>
        ))}
      </div>
      <p className="text-xs text-muted">Hit counts from the uploaded coverage report. Red lines never ran in the test suite.</p>
    </div>
  );
}

export function EvidenceCard({ evidence, active }: { evidence: Evidence; active?: boolean }) {
  const lang = languageForPath(evidence.file);
  const problems = asStrings(evidence.data.problems);
  const resolution = typeof evidence.data.resolution === "string" ? evidence.data.resolution : null;
  const isPairDiff = evidence.type === "diff_hunk" && evidence.excerpt_start_line == null && evidence.excerpt?.match(/^[+-]/);
  const message = typeof evidence.data.message === "string" ? evidence.data.message : null;
  const url = typeof evidence.data.url === "string" ? evidence.data.url : null;

  return (
    <article
      id={`evidence-${evidence.id}`}
      className={cn(
        "rounded-[10px] border bg-raised p-3.5 transition-colors duration-200",
        active ? "border-signal shadow-[0_0_0_3px_var(--signal-tint)]" : "border-line",
      )}
    >
      <header className="mb-3 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <EvidenceTag id={evidence.id} active={active} />
        <span className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-muted">{TYPE_LABEL[evidence.type]}</span>
        <span className="min-w-0 flex-1 truncate text-[0.8125rem] font-medium text-ink" title={evidence.title}>
          {evidence.title}
        </span>
      </header>
      {evidence.type === "signature_change" ? (
        <SignatureDiff evidence={evidence} />
      ) : isPairDiff && evidence.excerpt ? (
        <MiniDiff excerpt={evidence.excerpt} />
      ) : evidence.excerpt ? (
        <CodeExcerpt
          code={evidence.excerpt}
          startLine={evidence.excerpt_start_line}
          highlight={evidence.highlight_lines}
          lang={lang}
          maxHeight={320}
        />
      ) : null}
      {evidence.type === "coverage" && <div className="mt-3"><CoverageStrip evidence={evidence} /></div>}
      {(problems.length > 0 || message || resolution) && (
        <div className="mt-3 space-y-1.5">
          {message && <p className="text-[0.8125rem] text-ink-soft">{renderInlineCode(message)}</p>}
          {problems.map((p) => (
            <p key={p} className="flex gap-2 text-[0.8125rem] text-danger">
              <span aria-hidden="true">×</span>
              <span>{renderInlineCode(p)}</span>
            </p>
          ))}
          {resolution && (
            <Pill tone={resolution === "resolved" ? "neutral" : "signal"} className="h-5 text-[0.6875rem]">
              {resolution === "resolved" ? "Resolved through an import" : "Matched by method name only"}
            </Pill>
          )}
        </div>
      )}
      <footer className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] text-faint">
        {evidence.file && (
          <span className="font-mono">
            {formatLocation(evidence.file, evidence.start_line, evidence.end_line)}
            {evidence.side === "base" && " (before the change)"}
          </span>
        )}
        <span>Source: {evidence.source}</span>
        {url && (
          <a href={url} target="_blank" rel="noreferrer noopener" className="underline decoration-line-strong underline-offset-2 hover:text-ink">
            Rule documentation
          </a>
        )}
      </footer>
    </article>
  );
}
