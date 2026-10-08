"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

import { ApiError } from "./api/client";

interface Entry {
  data: unknown;
  error: ApiError | undefined;
  loading: boolean;
  /** When data was last fetched successfully (ms since epoch); 0 if never. */
  at: number;
}

// A tiny external store shared by every component that reads the same key, so
// two components asking for /meta trigger one request and see the same result.
const store = new Map<string, Entry>();
const listeners = new Map<string, Set<() => void>>();
const inflight = new Map<string, Promise<void>>();

function emit(key: string) {
  listeners.get(key)?.forEach((listener) => listener());
}

function put(key: string, patch: Partial<Entry>) {
  const prev = store.get(key) ?? { data: undefined, error: undefined, loading: false, at: 0 };
  store.set(key, { ...prev, ...patch });
  emit(key);
}

function fetchInto(key: string, fetcher: () => Promise<unknown>): Promise<void> {
  const running = inflight.get(key);
  if (running) return running;
  put(key, { loading: true, error: undefined });
  const promise = fetcher()
    .then((data) => put(key, { data, error: undefined, loading: false, at: Date.now() }))
    .catch((error: unknown) =>
      put(key, { loading: false, error: error instanceof ApiError ? error : new ApiError(0, { detail: String(error) }) }),
    )
    .finally(() => inflight.delete(key));
  inflight.set(key, promise);
  return promise;
}

/**
 * Minimal data hook: fetch on mount, share results between components for
 * `maxAgeMs`, expose reload(). The server snapshot is always "not loaded", so
 * hydration matches the server HTML even when another component already has data.
 */
export function useResource<T>(key: string | null, fetcher: () => Promise<T>, { maxAgeMs = 30_000 } = {}) {
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const subscribe = useCallback(
    (listener: () => void) => {
      if (!key) return () => {};
      const set = listeners.get(key) ?? new Set();
      set.add(listener);
      listeners.set(key, set);
      return () => set.delete(listener);
    },
    [key],
  );
  const entry = useSyncExternalStore(
    subscribe,
    () => (key ? store.get(key) : undefined),
    () => undefined,
  );

  const load = useCallback(async () => {
    if (!key) return;
    await fetchInto(key, () => fetcherRef.current());
  }, [key]);

  useEffect(() => {
    if (!key) return;
    const current = store.get(key);
    const fresh = current && current.at > 0 && Date.now() - current.at < maxAgeMs;
    if (!fresh) void fetchInto(key, () => fetcherRef.current());
  }, [key, maxAgeMs]);

  return {
    data: entry?.data as T | undefined,
    error: entry?.error,
    loading: Boolean(key) && (!entry || entry.loading || (entry.data === undefined && !entry.error)),
    reload: load,
  };
}

/** Mark results whose key starts with `prefix` as stale. Data stays visible; the next mount or reload() refetches. */
export function invalidate(prefix: string) {
  for (const [key, entry] of store) {
    if (key.startsWith(prefix)) {
      store.set(key, { ...entry, at: 0 });
      emit(key);
    }
  }
}
