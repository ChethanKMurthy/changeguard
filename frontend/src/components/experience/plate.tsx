import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** A figure plate: hairline frame, mono specimen label, optional metadata on the right. */
export function Plate({
  label,
  meta,
  children,
  className,
  bodyClassName,
}: {
  label?: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-[14px] border border-line bg-raised", className)}>
      {(label || meta) && (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-2.5">
          <span className="font-mono text-[0.6875rem] text-muted">{label}</span>
          {meta && <span className="font-mono text-[0.625rem] text-faint">{meta}</span>}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </div>
  );
}

/** Stage tag shown above a chapter heading: which pipeline stage(s) it covers, with recorded timings. */
export function StageTag({ n, stages }: { n: string; stages: { label: string; ms?: number | null }[] }) {
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[0.6875rem] text-muted">
      <span className="flex h-5 min-w-7 items-center justify-center rounded-[5px] bg-ink px-1.5 font-semibold text-bg numeric">{n}</span>
      {stages.map((s, i) => (
        <span key={s.label} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-faint" aria-hidden="true">+</span>}
          <span className="text-ink-soft">{s.label}</span>
          {s.ms != null && <span className="text-faint numeric">{formatMs(s.ms)}</span>}
        </span>
      ))}
    </p>
  );
}

function formatMs(ms: number) {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)} s`;
  if (ms < 10) return `${ms.toFixed(2)} ms`;
  return `${Math.round(ms)} ms`;
}
