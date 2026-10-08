"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { useResource } from "@/lib/use-resource";

import { Wordmark } from "./logo";
import { ThemeToggle } from "./theme-toggle";

const NAV = [
  { href: "/experience", label: "Experience" },
  { href: "/analyze", label: "Analyse" },
  { href: "/history", label: "Reports" },
  { href: "/evaluation", label: "Evaluation" },
  { href: "/method", label: "Method" },
];

function EngineStatus() {
  const { data, error, loading } = useResource("meta", api.meta, { maxAgeMs: 60_000 });
  const online = Boolean(data) && !error;
  const demo = error?.code === "engine_not_configured";
  const ai = data?.ai;
  const label = loading ? "Connecting" : online ? "Engine online" : demo ? "Demo mode" : "Engine offline";
  const detail = online
    ? `v${data?.version} · ruleset ${data?.ruleset_version} · AI: ${ai?.provider === "none" ? "off" : `${ai?.provider}${ai?.model ? ` / ${ai.model}` : ""}`}`
    : error?.message ?? "Checking the analysis engine…";
  return (
    <span
      className="hidden items-center gap-2 rounded-full border border-line px-2.5 py-1 text-xs text-muted lg:inline-flex"
      title={detail}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          loading && "animate-indicator bg-faint",
          !loading && online && "bg-ok",
          !loading && !online && (demo ? "bg-signal-glow" : "bg-danger"),
        )}
        aria-hidden="true"
      />
      <span className="numeric">{label}</span>
      {online && data && <span className="font-mono text-[0.6875rem] text-faint">{data.ruleset_version}</span>}
    </span>
  );
}

/** Static header used while the client header (which reads the URL) streams in. Same geometry, no layout shift. */
export function SiteHeaderShell() {
  return (
    <header className="sticky top-0 z-30 border-b border-transparent bg-bg">
      <div className="mx-auto flex h-16 max-w-[1240px] items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="rounded-md" aria-label="ChangeGuard home">
          <Wordmark />
        </Link>
        <nav aria-label="Primary" className="hidden flex-1 items-center gap-1 md:flex">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="relative rounded-md px-3 py-1.5 text-[0.9375rem] text-muted">
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  // The menu belongs to the page it was opened on, so navigating closes it without an effect.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-30 border-b transition-[border-color,background-color] duration-200",
        scrolled || open ? "border-line bg-bg/92 backdrop-blur-md" : "border-transparent bg-bg",
      )}
    >
      <div className="mx-auto flex h-16 max-w-[1240px] items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="rounded-md" aria-label="ChangeGuard home">
          <Wordmark />
        </Link>
        <nav aria-label="Primary" className="hidden flex-1 items-center gap-1 md:flex">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`) || (item.href === "/history" && pathname.startsWith("/reports"));
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative rounded-md px-3 py-1.5 text-[0.9375rem] transition-colors duration-150",
                  active ? "text-ink" : "text-muted hover:text-ink",
                )}
              >
                {item.label}
                {active && <span className="absolute inset-x-3 -bottom-[17px] h-[2px] rounded-full bg-signal" aria-hidden="true" />}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2 md:ml-0">
          <EngineStatus />
          <ThemeToggle />
          <Link
            href="/analyze"
            className="hidden h-9 items-center rounded-md bg-ink px-3.5 text-sm font-medium text-bg transition-opacity duration-150 hover:opacity-90 sm:inline-flex"
          >
            Analyse a diff
          </Link>
          <button
            type="button"
            className="inline-flex size-9 items-center justify-center rounded-md text-ink hover:bg-surface-2 md:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpenOn(open ? null : pathname)}
          >
            <svg viewBox="0 0 20 20" className="size-5" aria-hidden="true">
              {open ? (
                <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
              ) : (
                <path d="M3 6h14M3 10h14M3 14h14" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
              )}
            </svg>
          </button>
        </div>
      </div>
      {open && (
        <nav id="mobile-nav" aria-label="Mobile" className="border-t border-line px-4 pb-4 pt-2 md:hidden">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="block rounded-md px-2 py-2.5 text-base text-ink hover:bg-surface-2"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
