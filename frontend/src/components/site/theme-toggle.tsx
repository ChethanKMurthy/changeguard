"use client";

import { useSyncExternalStore } from "react";

import { cn } from "@/lib/cn";

type Theme = "system" | "light" | "dark";
const ORDER: Theme[] = ["system", "light", "dark"];
const LABEL: Record<Theme, string> = { system: "System theme", light: "Light theme", dark: "Dark theme" };

const listeners = new Set<() => void>();

function read(): Theme {
  try {
    const stored = localStorage.getItem("cg-theme");
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

function write(theme: Theme) {
  try {
    if (theme === "system") localStorage.removeItem("cg-theme");
    else localStorage.setItem("cg-theme", theme);
  } catch {
    // Storage may be unavailable (private mode); the choice still applies to this page.
  }
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function ThemeToggle({ className }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, read, () => "system" as Theme);
  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
  return (
    <button
      type="button"
      onClick={() => write(next)}
      className={cn(
        "inline-flex size-9 items-center justify-center rounded-md text-muted transition-colors duration-150 hover:bg-surface-2 hover:text-ink",
        className,
      )}
      aria-label={`${LABEL[theme]} (switch to ${LABEL[next].toLowerCase()})`}
      title={LABEL[theme]}
    >
      <svg viewBox="0 0 20 20" className="size-[18px]" aria-hidden="true">
        {theme === "light" && (
          <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
            <circle cx="10" cy="10" r="3.4" />
            {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
              <line
                key={a}
                x1={10 + Math.cos((a * Math.PI) / 180) * 6.2}
                y1={10 + Math.sin((a * Math.PI) / 180) * 6.2}
                x2={10 + Math.cos((a * Math.PI) / 180) * 7.8}
                y2={10 + Math.sin((a * Math.PI) / 180) * 7.8}
              />
            ))}
          </g>
        )}
        {theme === "dark" && (
          <path d="M14.8 12.6A6.3 6.3 0 0 1 7.4 5.2a6.3 6.3 0 1 0 7.4 7.4Z" fill="currentColor" />
        )}
        {theme === "system" && (
          <g>
            <circle cx="10" cy="10" r="6.6" fill="none" stroke="currentColor" strokeWidth="1.6" />
            <path d="M10 3.4a6.6 6.6 0 0 1 0 13.2Z" fill="currentColor" />
          </g>
        )}
      </svg>
    </button>
  );
}
