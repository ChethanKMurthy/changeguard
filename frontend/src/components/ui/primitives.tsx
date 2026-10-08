"use client";

import { Tabs as TabsPrimitive, Tooltip as TooltipPrimitive } from "radix-ui";
import { type ReactNode, useState } from "react";

import { cn } from "@/lib/cn";

export function Notice({
  tone = "neutral",
  title,
  children,
  className,
  action,
}: {
  tone?: "neutral" | "signal" | "danger" | "ai";
  title?: string;
  children?: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  const tones = {
    neutral: "border-line bg-surface",
    signal: "border-signal/35 bg-signal-tint",
    danger: "border-danger/35 bg-danger-tint",
    ai: "border-ai/35 bg-ai-tint",
  };
  const icon = {
    neutral: "i",
    signal: "!",
    danger: "×",
    ai: "✦",
  };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("flex gap-3 rounded-[10px] border p-4 text-sm", tones[tone], className)}>
      <span
        aria-hidden="true"
        className={cn(
          "mt-px flex size-5 shrink-0 items-center justify-center rounded-full border font-mono text-[0.6875rem] font-semibold",
          tone === "danger" ? "border-danger text-danger" : tone === "signal" ? "border-signal text-signal" : tone === "ai" ? "border-ai text-ai" : "border-line-strong text-muted",
        )}
      >
        {icon[tone]}
      </span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold text-ink">{title}</p>}
        {children && <div className={cn("text-ink-soft", title && "mt-1")}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <span className={cn("relative block overflow-hidden rounded-md bg-surface-2", className)} aria-hidden="true">
      <span className="animate-scan absolute inset-0 bg-gradient-to-r from-transparent via-bg/60 to-transparent" />
    </span>
  );
}

export function CopyButton({ value, label = "Copy", className }: { value: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-md border border-line bg-bg px-2 text-xs text-muted transition-colors duration-150 hover:border-line-strong hover:text-ink",
        className,
      )}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {
          setCopied(false);
        }
      }}
      aria-live="polite"
    >
      <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden="true">
        {copied ? (
          <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        ) : (
          <g fill="none" stroke="currentColor" strokeWidth="1.4">
            <rect x="5" y="5" width="8" height="8" rx="1.5" />
            <path d="M3 10V4.5A1.5 1.5 0 0 1 4.5 3H10" />
          </g>
        )}
      </svg>
      {copied ? "Copied" : label}
    </button>
  );
}

export function Tooltip({ content, children, side = "top" }: { content: ReactNode; children: ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TooltipPrimitive.Provider delayDuration={250}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side={side}
            sideOffset={6}
            className="z-[70] max-w-xs rounded-md bg-ink px-2.5 py-1.5 text-xs leading-relaxed text-bg shadow-float data-[state=delayed-open]:animate-in"
          >
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}

export const Tabs = TabsPrimitive.Root;

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <TabsPrimitive.List className={cn("flex items-center gap-1 relative overflow-x-auto border-b border-line scrollbar-thin", className)}>
      {children}
    </TabsPrimitive.List>
  );
}

export function TabsTrigger({ value, children, count }: { value: string; children: ReactNode; count?: number }) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className="group relative inline-flex h-11 shrink-0 items-center gap-2 px-3 text-sm text-muted transition-colors duration-150 hover:text-ink data-[state=active]:text-ink"
    >
      {children}
      {count !== undefined && (
        <span className="numeric rounded-full bg-surface-2 px-1.5 py-px text-[0.6875rem] text-muted group-data-[state=active]:bg-ink group-data-[state=active]:text-bg">
          {count}
        </span>
      )}
      <span className="absolute inset-x-2 -bottom-px h-[2px] scale-x-0 rounded-full bg-ink transition-transform duration-200 ease-[cubic-bezier(0.22,1,0.36,1)] group-data-[state=active]:scale-x-100" aria-hidden="true" />
    </TabsPrimitive.Trigger>
  );
}

export const TabsContent = TabsPrimitive.Content;

export function Figure({ children, caption, number, className }: { children: ReactNode; caption?: ReactNode; number?: string; className?: string }) {
  return (
    <figure className={className}>
      {children}
      {caption && (
        <figcaption className="mt-3 text-[0.8125rem] leading-relaxed text-muted">
          {number && <span className="mr-1.5 font-semibold text-ink">Fig. {number}</span>}
          {caption}
        </figcaption>
      )}
    </figure>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-line-strong bg-surface px-1 font-mono text-[0.625rem] text-muted">
      {children}
    </kbd>
  );
}
