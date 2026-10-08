import { cn } from "@/lib/cn";

/** Mark: an ink tile containing a delta (a change) with an amber indicator at its centre (observed). */
export function LogoMark({ className, title = "ChangeGuard" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7 shrink-0", className)} role="img" aria-label={title}>
      <rect x="1.5" y="1.5" width="29" height="29" rx="8" className="fill-ink" />
      <path
        d="M16 7.6 L24.6 23.2 H7.4 Z"
        fill="none"
        className="stroke-bg"
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="17.6" r="2.6" className="fill-signal-glow" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="text-[1.0625rem] font-[640] tracking-[-0.02em] [font-stretch:115%]">ChangeGuard</span>
    </span>
  );
}
