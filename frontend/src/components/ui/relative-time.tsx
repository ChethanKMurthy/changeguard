"use client";

import { useSyncExternalStore } from "react";

import { formatRelative } from "@/lib/format";

// One shared clock for every <RelativeTime>, ticking while any is mounted.
let now = 0;
let timer: ReturnType<typeof setInterval> | undefined;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (timer === undefined) {
    timer = setInterval(() => {
      now = Date.now();
      listeners.forEach((l) => l());
    }, 30_000);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== undefined) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

function getSnapshot() {
  if (now === 0) now = Date.now();
  return now;
}

/**
 * "3 min ago", computed only in the browser. Prerendered and server HTML show
 * the absolute date, so static pages never bake in the build time's "now".
 */
export function RelativeTime({ iso }: { iso: string }) {
  const current = useSyncExternalStore(subscribe, getSnapshot, () => 0);
  return (
    <time dateTime={iso} title={iso}>
      {current ? formatRelative(iso, new Date(current)) : iso.slice(0, 10)}
    </time>
  );
}
