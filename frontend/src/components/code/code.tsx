"use client";

import { useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/cn";
import { type TokenLine, tokenize } from "@/lib/highlight";

import { CopyButton } from "../ui/primitives";

/** Highlight a block of code; falls back to plain text while loading or for unsupported languages. */
export function useTokens(code: string, lang: string): TokenLine[] | null {
  const [tokens, setTokens] = useState<{ key: string; lines: TokenLine[] | null } | null>(null);
  const key = `${lang}\u0000${code}`;
  useEffect(() => {
    let cancelled = false;
    void tokenize(code, lang).then((lines) => {
      if (!cancelled) setTokens({ key, lines });
    });
    return () => {
      cancelled = true;
    };
  }, [code, lang, key]);
  return tokens?.key === key ? tokens.lines : null;
}

export function TokenText({ tokens, fallback }: { tokens: TokenLine | undefined; fallback: string }) {
  if (!tokens) return <>{fallback || " "}</>;
  if (tokens.length === 0) return <>{" "}</>;
  return (
    <>
      {tokens.map((token, i) => (
        <span
          key={i}
          style={{
            color: token.color,
            fontStyle: token.fontStyle && token.fontStyle & 1 ? "italic" : undefined,
            fontWeight: token.fontStyle && token.fontStyle & 2 ? 600 : undefined,
          }}
        >
          {token.content}
        </span>
      ))}
    </>
  );
}

/**
 * A verbatim source excerpt with real line numbers and highlighted lines.
 * Used for evidence: the numbers shown are the numbers in the file.
 */
export function CodeExcerpt({
  code,
  startLine,
  highlight = [],
  lang,
  className,
  maxHeight,
}: {
  code: string;
  startLine?: number | null;
  highlight?: number[];
  lang: string;
  className?: string;
  maxHeight?: number;
}) {
  const lines = useMemo(() => code.split("\n"), [code]);
  const tokens = useTokens(code, lang);
  const marked = new Set(highlight);
  const first = startLine ?? 1;
  const width = String(first + lines.length - 1).length;
  return (
    <div
      className={cn("relative overflow-auto rounded-md border border-line bg-surface font-mono text-[0.78rem] leading-[1.7] scrollbar-thin", className)}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((line, i) => {
            const number = first + i;
            const hot = startLine != null && marked.has(number);
            return (
              <tr key={i} className={cn(hot && "bg-highlight")}>
                <td
                  className={cn(
                    "select-none border-r border-line px-2.5 text-right align-top numeric",
                    hot ? "text-ink" : "text-faint",
                  )}
                  style={{ width: `${width + 2}ch` }}
                >
                  {startLine != null ? number : ""}
                </td>
                <td className="relative whitespace-pre px-3 align-top">
                  {hot && <span className="absolute inset-y-0 left-0 w-[2px] bg-signal" aria-hidden="true" />}
                  <TokenText tokens={tokens?.[i]} fallback={line} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** A copyable code block (suggested tests, commands). */
export function CodeBlock({ code, lang, title, className }: { code: string; lang: string; title?: string; className?: string }) {
  const tokens = useTokens(code, lang);
  const lines = code.split("\n");
  return (
    <div className={cn("overflow-hidden rounded-md border border-line bg-surface", className)}>
      <div className="flex items-center justify-between gap-3 border-b border-line px-3 py-1.5">
        <span className="font-mono text-[0.6875rem] text-muted">{title ?? lang}</span>
        <CopyButton value={code} />
      </div>
      <pre className="relative overflow-x-auto px-3 py-2.5 font-mono text-[0.78rem] leading-[1.7] scrollbar-thin">
        <code>
          {lines.map((line, i) => (
            <span key={i} className="block min-h-[1.7em]">
              <TokenText tokens={tokens?.[i]} fallback={line} />
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}
