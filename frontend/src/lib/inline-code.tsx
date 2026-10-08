import type { ReactNode } from "react";

/**
 * Render `backticked` fragments as inline code. Safe for untrusted text: every
 * fragment becomes a React text node (never HTML). Usable from server and
 * client components alike.
 */
export function renderInlineCode(text: string, codeClassName = "rounded bg-surface-2 px-1 py-px font-mono text-[0.86em] text-ink"): ReactNode[] {
  return text.split(/(`[^`]+`)/g).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 2 ? (
      <code key={i} className={codeClassName}>
        {part.slice(1, -1)}
      </code>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}
