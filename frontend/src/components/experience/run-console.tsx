"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import type { InputsFigure, RecordedRun } from "@/lib/experience-data";
import { formatDuration, PRIORITY_META } from "@/lib/format";
import { initialStages, type StageView } from "@/lib/stages";
import { useAnalysisRun } from "@/lib/use-analysis-run";
import { useResource } from "@/lib/use-resource";

import { Button } from "../ui/button";
import { PipelineTrack } from "../viz/pipeline-track";

const EASE = [0.22, 1, 0.36, 1] as const;
/** Reveal cadence. Durations shown are measured; only the reveal is paced so a person can follow it. */
const STEP_MS = 190;

type Mode = "idle" | "replay" | "live";

interface LiveResult {
  id: string;
  findings: number;
  findingIds: string[];
  priority: string;
  ruleset: string;
  aiStatus: string;
  aiClaims?: { accepted: number; total: number };
}

type LogLine = { tag: string; name: string; detail: string; tone?: "danger" | "signal" | "faint" };

function EventLog({ lines }: { lines: LogLine[] }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);
  return (
    <div className="mt-5 flex min-h-[176px] flex-1 flex-col">
      <p className="mb-1.5 text-[0.6875rem] font-medium text-muted">Event log</p>
      <div
        ref={box}
        className="max-h-[260px] min-h-[150px] flex-1 overflow-y-auto rounded-[8px] border border-line bg-surface px-3 py-2 font-mono text-[0.6875rem] leading-[1.75] scrollbar-thin lg:max-h-none"
        role="log"
        aria-label="Run events"
      >
        {lines.length === 0 ? (
          <p className="text-faint">waiting</p>
        ) : (
          lines.map((line, i) => (
            <p key={i} className="grid grid-cols-[60px_minmax(0,1fr)_auto] gap-2">
              <span className={cn(line.tone === "danger" ? "text-danger" : line.tone === "signal" ? "text-signal" : line.tone === "faint" ? "text-faint" : "text-ok")}>
                {line.tag}
              </span>
              <span className={cn("truncate", line.tone === "faint" ? "text-faint" : "text-ink")}>{line.name}</span>
              <span className="text-right text-muted numeric">{line.detail}</span>
            </p>
          ))
        )}
      </div>
    </div>
  );
}

function completedPrefix(stages: StageView[]): number {
  const i = stages.findIndex((s) => s.status === "pending" || s.status === "running");
  return i === -1 ? stages.length : i;
}

function formatBytes(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

export function RunConsole({ sampleId, recorded, inputs }: { sampleId: string; recorded: RecordedRun; inputs: InputsFigure }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const meta = useResource("meta", api.meta, { maxAgeMs: 60_000 });
  const run = useAnalysisRun();
  const [mode, setMode] = useState<Mode>("idle");
  const [shown, setShown] = useState(0);
  const [withAI, setWithAI] = useState(false);
  const [live, setLive] = useState<LiveResult | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);

  const online = Boolean(meta.data) && !meta.error;
  const demo = meta.error?.code === "engine_not_configured";
  const aiAvailable = Boolean(meta.data?.ai.configured && meta.data.ai.reachable !== false && meta.data.ai.model_available !== false);
  const target = mode === "live" ? run.state.stages : mode === "replay" ? recorded.stages : initialStages();
  const available = mode === "live" ? completedPrefix(run.state.stages) : mode === "replay" ? recorded.stages.length : 0;
  const total = target.length;

  // Pace the reveal: one stage every STEP_MS until the display catches up with what has actually completed.
  useEffect(() => {
    if (mode === "idle" || shown >= available) return;
    const timer = window.setTimeout(() => setShown((n) => n + 1), reduce ? 0 : STEP_MS);
    return () => window.clearTimeout(timer);
  }, [mode, shown, available, reduce]);

  const { reset } = run;
  const startReplay = useCallback(() => {
    reset();
    setLive(null);
    setLiveError(null);
    setShown(0);
    setMode("replay");
  }, [reset]);

  // Play the recording once when the figure first comes into view.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        observer.disconnect();
        setMode((m) => (m === "idle" ? "replay" : m));
      },
      // Start as soon as the top of the console is comfortably on screen; the figure is taller than most viewports.
      { rootMargin: "0px 0px -20% 0px", threshold: 0 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const startLive = async () => {
    setLive(null);
    setLiveError(null);
    setShown(0);
    setMode("live");
    const id = await run.start(() => api.runSample(sampleId, { ai: withAI && aiAvailable }));
    if (!id) setLiveError("The engine did not accept the run.");
  };

  // When the live run finishes, load its report and compare finding IDs with the recording.
  const liveId = run.state.analysisId;
  const livePhase = run.state.phase;
  useEffect(() => {
    if (mode !== "live" || livePhase !== "completed" || !liveId) return;
    let cancelled = false;
    api
      .analysis(liveId)
      .then((detail) => {
        if (cancelled || !detail.report) return;
        const report = detail.report;
        setLive({
          id: liveId,
          findings: report.findings.length,
          findingIds: report.findings.filter((f) => f.kind !== "ai").map((f) => f.id),
          priority: report.summary.review_priority.level,
          ruleset: report.ruleset_version,
          aiStatus: report.ai.status,
          aiClaims: report.ai.verification
            ? { accepted: report.ai.verification.claims_accepted, total: report.ai.verification.claims_total }
            : undefined,
        });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLiveError(error instanceof Error ? error.message : "Could not load the live report.");
      });
    return () => {
      cancelled = true;
    };
  }, [mode, livePhase, liveId]);

  const display: StageView[] = useMemo(
    () =>
      target.map((stage, i) => {
        if (i < shown) return stage;
        const active = mode !== "idle" && i === shown && (mode === "replay" || run.state.phase === "running" || i < available);
        return { name: stage.name, label: stage.label, status: active ? "running" : "pending" };
      }),
    [target, shown, mode, available, run.state.phase],
  );

  const failed = mode === "live" && (run.state.phase === "failed" || liveError);
  const replayDone = mode === "replay" && shown >= total;
  const liveDone = mode === "live" && shown >= total && Boolean(live);
  const busy = mode === "live" && !failed && !liveDone;

  const comparison = useMemo(() => {
    if (!live) return null;
    const recordedSet = new Set(recorded.findingIds);
    const matched = live.findingIds.filter((id) => recordedSet.has(id)).length;
    return {
      matched,
      missing: recorded.findingIds.length - matched,
      extra: live.findingIds.length - matched,
      identical: matched === recorded.findingIds.length && live.findingIds.length === recorded.findingIds.length,
    };
  }, [live, recorded.findingIds]);

  const elapsed = mode === "live" ? run.state.durationMs : recorded.totalMs;

  // A plain-text log of the run, derived from the same events that drive the pipeline view.
  const log: LogLine[] = [];
  if (mode === "replay") log.push({ tag: "replay", name: recorded.analysisId, detail: "recorded" });
  if (mode === "live") {
    log.push({ tag: "POST", name: `/samples/${sampleId}/analyses`, detail: withAI && aiAvailable ? "ai=true" : "ai=false" });
    if (run.state.analysisId) {
      log.push({ tag: "202", name: run.state.analysisId, detail: "accepted" });
      log.push({ tag: "SSE", name: "events", detail: "streaming" });
    }
  }
  display.forEach((stage, i) => {
    if (i >= shown) return;
    log.push({
      tag: stage.status === "ok" ? "ok" : stage.status,
      name: stage.name,
      detail: stage.status === "skipped" ? "skipped" : formatDuration(stage.durationMs),
      tone: stage.status === "failed" ? "danger" : stage.status === "skipped" ? "faint" : undefined,
    });
  });
  if (replayDone) log.push({ tag: "done", name: `${recorded.findings} findings`, detail: `priority ${recorded.priority}`, tone: "signal" });
  if (liveDone && live) log.push({ tag: "done", name: `${live.findings} findings`, detail: `priority ${live.priority}`, tone: "signal" });
  if (failed) log.push({ tag: "error", name: run.state.error?.code ?? "run", detail: run.state.error?.message ?? liveError ?? "", tone: "danger" });

  return (
    <div ref={ref} className="relative overflow-hidden rounded-[14px] border border-line-strong bg-raised shadow-float">
      {/* Header strip */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-line px-4 py-2.5">
        <span className="flex items-center gap-2 font-mono text-[0.6875rem] text-muted">
          <span className={cn("size-1.5 rounded-full", busy ? "animate-indicator bg-signal-glow" : "bg-signal-glow")} aria-hidden="true" />
          {sampleId}
          <span className="text-faint">·</span>
          <span className="text-faint">SAMPLE · SYNTHETIC</span>
        </span>
        <span className="flex items-center gap-2 text-[0.6875rem] text-muted">
          <span
            className={cn("size-1.5 rounded-full", meta.loading ? "animate-indicator bg-faint" : online ? "bg-ok" : "bg-line-strong")}
            aria-hidden="true"
          />
          {meta.loading
            ? "Looking for an engine…"
            : online
              ? `Engine online · ruleset ${meta.data?.ruleset_version}`
              : demo
                ? "Demo deployment · recording only"
                : "No engine reachable · recording only"}
        </span>
      </div>

      <div className="grid lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
        {/* Inputs and controls */}
        <div className="flex flex-col border-b border-line p-5 lg:border-b-0 lg:border-r">
          <h3 className="text-[0.8125rem] font-semibold text-ink">Inputs</h3>
          <ul className="mt-3 space-y-2.5 text-[0.8125rem]">
            <li className="grid grid-cols-[112px_minmax(0,1fr)] gap-3">
              <span className="font-mono text-[0.75rem] text-ink">change.patch</span>
              <span className="min-w-0 text-muted">
                git patch · {inputs.changed.length} files ·{" "}
                <span className="numeric text-ok">+{inputs.additions}</span> <span className="numeric text-danger">−{inputs.deletions}</span>
                <span className="mt-0.5 block truncate font-mono text-[0.6875rem] text-faint" title={`sha256 ${inputs.patchSha}`}>
                  sha256 {inputs.patchSha.slice(0, 16)}…
                </span>
              </span>
            </li>
            <li className="grid grid-cols-[112px_minmax(0,1fr)] gap-3">
              <span className="font-mono text-[0.75rem] text-ink">snapshot.zip</span>
              <span className="text-muted">
                repository before the change · {inputs.snapshotFiles} files · {formatBytes(inputs.snapshotBytes)}
              </span>
            </li>
            {inputs.coverageFilename && (
              <li className="grid grid-cols-[112px_minmax(0,1fr)] gap-3">
                <span className="font-mono text-[0.75rem] text-ink">{inputs.coverageFilename}</span>
                <span className="text-muted">{inputs.coverageFormat === "cobertura" ? "Cobertura" : inputs.coverageFormat} report from the test suite</span>
              </li>
            )}
          </ul>

          <div className="mt-6 space-y-3 border-t border-line pt-5">
            <div className="flex flex-wrap gap-2">
              <Button onClick={startLive} disabled={!online || busy} loading={busy} size="md">
                {busy ? "Running on your engine" : "Run it on your engine"}
              </Button>
              <Button variant="secondary" onClick={startReplay} disabled={busy}>
                Replay the recording
              </Button>
            </div>
            {online && (
              <label
                className={cn("flex w-fit items-center gap-2.5 text-[0.8125rem]", aiAvailable ? "cursor-pointer text-ink-soft" : "cursor-not-allowed text-faint")}
                title={aiAvailable ? undefined : meta.data?.ai.detail ?? "No AI provider configured"}
              >
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={withAI && aiAvailable}
                  disabled={!aiAvailable || busy}
                  onChange={(e) => setWithAI(e.target.checked)}
                />
                <span className="relative h-5 w-9 rounded-full bg-line-strong transition-colors duration-150 peer-checked:bg-ai peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-signal">
                  <span
                    className={cn(
                      "absolute left-0.5 top-0.5 size-4 rounded-full bg-bg transition-transform duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]",
                      withAI && aiAvailable && "translate-x-4",
                    )}
                  />
                </span>
                <span>
                  <span className="text-ai" aria-hidden="true">✦</span> Include AI synthesis
                  {aiAvailable && meta.data?.ai.model && <span className="ml-1.5 font-mono text-[0.6875rem] text-muted">{meta.data.ai.model}</span>}
                </span>
              </label>
            )}
            <p className="max-w-[46ch] text-xs leading-relaxed text-muted">
              {online
                ? "A live run sends the bundled sample to your engine and streams its progress. The recording was made by the same engine at build time."
                : demo
                  ? "This public demo has no analysis engine attached, so the figure replays a run the engine recorded at build time. Run ChangeGuard locally to analyse live."
                  : "Start the engine to run the sample live. Until then the figure replays a run recorded by the engine at build time."}
            </p>
          </div>
          <EventLog lines={log} />
        </div>

        {/* Pipeline */}
        <div className="p-5">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <h3 className="text-[0.8125rem] font-semibold text-ink">
              Pipeline
              <span className="ml-2 font-normal text-muted">
                {mode === "live" ? "live" : mode === "replay" ? "recording" : "ready"}
              </span>
            </h3>
            <span className="font-mono text-[0.625rem] text-faint">paced for reading · times measured</span>
          </div>
          <PipelineTrack stages={display} />
        </div>
      </div>

      {/* Result strip */}
      <div className="min-h-[68px] border-t border-line bg-surface px-5 py-3.5" aria-live="polite">
        <AnimatePresence mode="wait" initial={false}>
          {failed ? (
            <motion.p key="failed" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-[0.8125rem] text-danger">
              {run.state.error?.message ?? liveError}
            </motion.p>
          ) : replayDone || liveDone ? (
            <motion.div
              key={`${mode}-done`}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3, ease: EASE }}
              className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3"
            >
              <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-[0.8125rem] text-muted">
                <span>
                  <span className="text-2xl font-[650] tracking-[-0.03em] text-ink numeric [font-stretch:112%]">
                    {mode === "live" && live ? live.findings : recorded.findings}
                  </span>{" "}
                  findings
                </span>
                <span>
                  priority{" "}
                  <span className="font-semibold text-signal">
                    {PRIORITY_META[mode === "live" && live ? live.priority : recorded.priority]?.label}
                  </span>
                </span>
                <span>
                  <span className="font-mono text-ink numeric">{formatDuration(elapsed)}</span> {mode === "live" ? "end to end" : "of stage time"}
                </span>
                {mode === "live" && live && comparison && (
                  <span className={cn("flex items-center gap-1.5", comparison.identical ? "text-ok" : "text-signal")}>
                    <span aria-hidden="true">{comparison.identical ? "✓" : "≠"}</span>
                    {comparison.identical
                      ? `All ${comparison.matched} finding IDs match the recording`
                      : `${comparison.matched} of ${recorded.findingIds.length} finding IDs match the recording${
                          live.ruleset !== recorded.ruleset ? ` (live ruleset ${live.ruleset}, recorded ${recorded.ruleset})` : ""
                        }`}
                  </span>
                )}
                {mode === "live" && live?.aiStatus === "completed" && live.aiClaims && (
                  <span className="text-ai">
                    ✦ {live.aiClaims.accepted} of {live.aiClaims.total} AI claims verified
                  </span>
                )}
              </div>
              <Link
                href={mode === "live" && live ? `/reports/${live.id}` : "/reports/sample"}
                className="text-[0.8125rem] font-medium text-ink underline decoration-line-strong underline-offset-[3px] hover:decoration-signal"
              >
                {mode === "live" ? "Open the live report" : "Open the recorded report"} →
              </Link>
            </motion.div>
          ) : (
            <motion.p key="waiting" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="text-[0.8125rem] text-muted">
              {mode === "idle"
                ? "Ready."
                : mode === "live" && run.state.phase === "submitting"
                  ? "Submitting the sample…"
                  : `Stage ${Math.min(shown + 1, total)} of ${total}: ${target[Math.min(shown, total - 1)]?.label ?? ""}`}
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
