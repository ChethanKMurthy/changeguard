import type { Confidence, Provenance, Severity } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { PROVENANCE_META, SEVERITY_LABEL } from "@/lib/format";

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
  info: "bg-sev-info",
};

const SEVERITY_TEXT: Record<Severity, string> = {
  critical: "text-sev-critical",
  high: "text-sev-high",
  medium: "text-sev-medium-ink",
  low: "text-sev-low",
  info: "text-muted",
};

/** Severity marker: a shaped glyph (not colour alone) plus a text label. */
export function SeverityMark({ severity, className }: { severity: Severity; className?: string }) {
  // Shape encodes rank so the marker survives greyscale and colour-vision deficiencies.
  const shape =
    severity === "critical" ? (
      <path d="M5 0.6 9.4 5 5 9.4 0.6 5Z" />
    ) : severity === "high" ? (
      <path d="M5 1 9.2 8.6H0.8Z" />
    ) : severity === "medium" ? (
      <rect x="1.4" y="1.4" width="7.2" height="7.2" rx="1" />
    ) : severity === "low" ? (
      <circle cx="5" cy="5" r="3.6" />
    ) : (
      <circle cx="5" cy="5" r="2.4" />
    );
  return (
    <svg viewBox="0 0 10 10" className={cn("size-2.5 shrink-0", SEVERITY_TEXT[severity], className)} aria-hidden="true">
      <g fill="currentColor">{shape}</g>
    </svg>
  );
}

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-semibold", SEVERITY_TEXT[severity], className)}>
      <SeverityMark severity={severity} />
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

export function SeverityDot({ severity }: { severity: Severity }) {
  return <span className={cn("inline-block size-2 rounded-full", SEVERITY_DOT[severity])} aria-hidden="true" />;
}

const PROVENANCE_STYLE: Record<Provenance, string> = {
  deterministic: "border-ink/80 bg-ink text-bg",
  heuristic: "border-line-strong bg-bg text-ink",
  ai: "border-ai/40 bg-ai-tint text-ai",
};

export function ProvenanceBadge({ kind, compact, className }: { kind: Provenance; compact?: boolean; className?: string }) {
  const meta = PROVENANCE_META[kind];
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1 rounded-[5px] border px-1.5 text-[0.6875rem] font-semibold leading-none tracking-[0.01em]",
        PROVENANCE_STYLE[kind],
        className,
      )}
      title={meta.description}
    >
      <span aria-hidden="true" className="text-[0.625rem]">
        {meta.glyph}
      </span>
      {compact ? meta.short : meta.label}
    </span>
  );
}

export function ProvenanceGlyph({ kind, className }: { kind: Provenance; className?: string }) {
  return (
    <span
      aria-label={PROVENANCE_META[kind].label}
      title={PROVENANCE_META[kind].label}
      className={cn(kind === "ai" ? "text-ai" : kind === "heuristic" ? "text-muted" : "text-ink", className)}
    >
      {PROVENANCE_META[kind].glyph}
    </span>
  );
}

const CONFIDENCE_STEPS: Record<Confidence, number> = { high: 3, medium: 2, low: 1 };

/** Three-step meter: confidence is categorical, so it is drawn as steps, never as a percentage. */
export function ConfidenceMeter({ confidence, className }: { confidence: Confidence; className?: string }) {
  const filled = CONFIDENCE_STEPS[confidence];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs text-muted", className)}>
      <span className="flex items-end gap-[2px]" aria-hidden="true">
        {[1, 2, 3].map((step) => (
          <span
            key={step}
            className={cn("w-[3px] rounded-[1px]", step <= filled ? "bg-ink" : "bg-line-strong")}
            style={{ height: 4 + step * 3 }}
          />
        ))}
      </span>
      <span>
        <span className="sr-only">Confidence: </span>
        {confidence[0].toUpperCase() + confidence.slice(1)} confidence
      </span>
    </span>
  );
}

/** Evidence ID rendered as a specimen tag. */
export function EvidenceTag({ id, active, className, onClick }: { id: string; active?: boolean; className?: string; onClick?: () => void }) {
  const content = (
    <>
      <span className="size-1 rounded-full bg-current opacity-50" aria-hidden="true" />
      {id}
    </>
  );
  const style = cn(
    "inline-flex h-5 items-center gap-1 rounded-[4px] border px-1.5 font-mono text-[0.6875rem] leading-none transition-colors duration-150",
    active ? "border-signal bg-signal-tint text-ink" : "border-line-strong bg-surface text-ink-soft",
    onClick && "cursor-pointer hover:border-signal hover:text-ink",
    className,
  );
  if (onClick) {
    return (
      <button type="button" className={style} onClick={onClick} aria-label={`Evidence ${id}`}>
        {content}
      </button>
    );
  }
  return <span className={style}>{content}</span>;
}

export function Pill({ children, tone = "neutral", className }: { children: React.ReactNode; tone?: "neutral" | "signal" | "ai" | "ok" | "danger"; className?: string }) {
  const tones = {
    neutral: "border-line bg-surface text-ink-soft",
    signal: "border-signal/30 bg-signal-tint text-signal",
    ai: "border-ai/30 bg-ai-tint text-ai",
    ok: "border-ok/30 bg-ok-tint text-ok",
    danger: "border-danger/30 bg-danger-tint text-danger",
  };
  return (
    <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}
