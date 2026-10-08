import type {
  AnalysisDetail,
  AnalysisList,
  AnalysisSummary,
  Meta,
  Problem,
  RuleInfo,
  SampleDetail,
  SampleSummary,
  StageEvent,
} from "./types";

/** All requests go to the same origin; the Next.js route handler proxies them to the engine. */
export const API_BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly problem: Partial<Problem>;

  constructor(status: number, problem: Partial<Problem>) {
    super(problem.detail || problem.title || `Request failed (${status})`);
    this.status = status;
    this.code = problem.code || "http_error";
    this.problem = problem;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers: { Accept: "application/json", ...init?.headers } });
  } catch {
    throw new ApiError(0, {
      code: "network",
      title: "Engine unreachable",
      detail: "Could not reach the ChangeGuard engine. Check that the API is running.",
    });
  }
  if (!response.ok) {
    let problem: Partial<Problem> = { title: response.statusText };
    try {
      problem = (await response.json()) as Partial<Problem>;
    } catch {
      // Non-JSON error body (e.g. a proxy page); keep the status text.
    }
    throw new ApiError(response.status, problem);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  meta: () => request<Meta>("/meta"),
  rules: () => request<RuleInfo[]>("/rules"),
  samples: () => request<SampleSummary[]>("/samples"),
  sample: (id: string) => request<SampleDetail>(`/samples/${encodeURIComponent(id)}`),
  runSample: (id: string, opts: { ai?: boolean; snapshot?: boolean; coverage?: boolean } = {}) => {
    const params = new URLSearchParams({
      ai: String(Boolean(opts.ai)),
      snapshot: String(opts.snapshot ?? true),
      coverage: String(opts.coverage ?? true),
    });
    return request<AnalysisSummary>(`/samples/${encodeURIComponent(id)}/analyses?${params}`, { method: "POST" });
  },
  createAnalysis: (form: FormData) => request<AnalysisSummary>("/analyses", { method: "POST", body: form }),
  analysis: (id: string) => request<AnalysisDetail>(`/analyses/${encodeURIComponent(id)}`),
  analyses: (opts: { limit?: number; offset?: number; q?: string } = {}) => {
    const params = new URLSearchParams();
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.offset) params.set("offset", String(opts.offset));
    if (opts.q) params.set("q", opts.q);
    return request<AnalysisList>(`/analyses?${params}`);
  },
  deleteAnalysis: (id: string) => request<void>(`/analyses/${encodeURIComponent(id)}`, { method: "DELETE" }),
  exportUrl: (id: string, format: "json" | "markdown" | "sarif") =>
    `${API_BASE}/analyses/${encodeURIComponent(id)}/export?format=${format}`,
};

/**
 * Subscribe to an analysis's progress. Uses server-sent events, and falls back to
 * polling the analysis resource if the stream cannot be opened (some proxies buffer SSE).
 * Returns an unsubscribe function.
 */
export function subscribeToAnalysis(
  id: string,
  onEvent: (event: StageEvent) => void,
  onError?: (error: ApiError) => void,
): () => void {
  let closed = false;
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  const stream: { source?: EventSource } = {};
  let sawTerminal = false;

  const finishWith = (event: StageEvent) => {
    sawTerminal = true;
    onEvent(event);
    cleanup();
  };

  const poll = async () => {
    if (closed) return;
    try {
      const detail = await api.analysis(id);
      if (detail.status === "completed") {
        detail.report?.pipeline.forEach((stage) => onEvent({ type: "stage", ...stage }));
        finishWith({ type: "completed", analysis_id: id, duration_ms: detail.duration_ms ?? 0, summary: detail.summary ?? ({} as never) });
        return;
      }
      if (detail.status === "failed") {
        finishWith({ type: "failed", error: detail.error ?? { code: "failed", message: "Analysis failed." } });
        return;
      }
    } catch (error) {
      if (error instanceof ApiError) onError?.(error);
    }
    pollTimer = setTimeout(poll, 600);
  };

  const cleanup = () => {
    closed = true;
    stream.source?.close();
    if (pollTimer) clearTimeout(pollTimer);
  };

  if (typeof EventSource === "undefined") {
    void poll();
    return cleanup;
  }

  const source = new EventSource(`${API_BASE}/analyses/${encodeURIComponent(id)}/events`);
  stream.source = source;
  const handle = (message: MessageEvent<string>) => {
    try {
      const event = JSON.parse(message.data) as StageEvent;
      if (event.type === "completed" || event.type === "failed") finishWith(event);
      else onEvent(event);
    } catch {
      // Ignore malformed frames; the stream continues.
    }
  };
  for (const name of ["started", "stage", "completed", "failed"]) {
    source.addEventListener(name, handle as EventListener);
  }
  source.onerror = () => {
    if (sawTerminal || closed) return;
    // The stream dropped (or never opened): continue by polling.
    source.close();
    void poll();
  };
  return cleanup;
}
