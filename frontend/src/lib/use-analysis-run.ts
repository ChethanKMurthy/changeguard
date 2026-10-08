"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, subscribeToAnalysis } from "./api/client";
import type { AnalysisSummary, HistorySummary } from "./api/types";
import { initialStages, stageDetail, type StageView } from "./stages";

export type RunPhase = "idle" | "submitting" | "running" | "completed" | "failed";

export interface RunState {
  phase: RunPhase;
  analysisId?: string;
  stages: StageView[];
  error?: { code: string; message: string };
  durationMs?: number;
  summary?: HistorySummary;
}

const IDLE: RunState = { phase: "idle", stages: initialStages() };

/** Start an analysis (any request returning an AnalysisSummary) and follow its progress live. */
export function useAnalysisRun() {
  const [state, setState] = useState<RunState>(IDLE);
  const unsubscribe = useRef<(() => void) | null>(null);

  useEffect(() => () => unsubscribe.current?.(), []);

  const follow = useCallback((analysisId: string) => {
    unsubscribe.current?.();
    setState({ phase: "running", analysisId, stages: initialStages() });
    unsubscribe.current = subscribeToAnalysis(
      analysisId,
      (event) => {
        setState((prev) => {
          if (event.type === "stage") {
            const stages = prev.stages.map((stage) => {
              if (stage.name !== event.name) return stage;
              if (event.status === "running") return { ...stage, status: "running" as const };
              return {
                ...stage,
                status: event.status,
                durationMs: event.duration_ms,
                detail: stageDetail({ name: event.name, summary: event.summary ?? {}, status: event.status, notes: event.notes ?? [] }),
                notes: event.notes,
              };
            });
            return { ...prev, stages };
          }
          if (event.type === "completed") {
            return { ...prev, phase: "completed", durationMs: event.duration_ms, summary: event.summary };
          }
          if (event.type === "failed") {
            return {
              ...prev,
              phase: "failed",
              error: event.error,
              stages: prev.stages.map((s) => (s.status === "running" ? { ...s, status: "failed" as const } : s)),
            };
          }
          return prev;
        });
      },
      (error) => setState((prev) => ({ ...prev, error: { code: error.code, message: error.message } })),
    );
  }, []);

  const start = useCallback(
    async (request: () => Promise<AnalysisSummary>) => {
      setState({ phase: "submitting", stages: initialStages() });
      try {
        const created = await request();
        follow(created.id);
        return created.id;
      } catch (error) {
        const e = error instanceof ApiError ? error : new ApiError(0, { detail: String(error) });
        setState({ phase: "failed", stages: initialStages(), error: { code: e.code, message: e.message } });
        return undefined;
      }
    },
    [follow],
  );

  const reset = useCallback(() => {
    unsubscribe.current?.();
    setState(IDLE);
  }, []);

  return { state, start, follow, reset };
}
