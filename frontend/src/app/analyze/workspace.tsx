"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ArchiveIcon, Dropzone, formatBytes, GaugeIcon } from "@/components/analyze/dropzone";
import { Pill, SeverityMark } from "@/components/ui/badges";
import { Button, ButtonLink } from "@/components/ui/button";
import { CopyButton, Notice, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { PipelineTrack } from "@/components/viz/pipeline-track";
import { api } from "@/lib/api/client";
import type { Severity } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDuration, PRIORITY_META, SEVERITY_LABEL, SEVERITY_ORDER } from "@/lib/format";
import { STAGES } from "@/lib/stages";
import { useAnalysisRun } from "@/lib/use-analysis-run";
import { useResource } from "@/lib/use-resource";

const EASE = [0.22, 1, 0.36, 1] as const;

function patchStats(text: string) {
  if (!text.trim()) return null;
  const lines = text.split("\n");
  const files = new Set<string>();
  let additions = 0;
  let deletions = 0;
  for (const line of lines) {
    if (line.startsWith("+++ ")) files.add(line.slice(4));
    else if (line.startsWith("+") && !line.startsWith("+++")) additions++;
    else if (line.startsWith("-") && !line.startsWith("---")) deletions++;
  }
  const looksLikeDiff = /^(diff --git |--- |@@ )/m.test(text);
  return { files: files.size, additions, deletions, lines: lines.length, looksLikeDiff };
}

export function AnalyzeWorkspace() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const meta = useResource("meta", api.meta, { maxAgeMs: 60_000 });
  const samples = useResource("samples", api.samples, { maxAgeMs: 300_000 });
  const run = useAnalysisRun();

  const [mode, setMode] = useState<"paste" | "upload">("paste");
  const [patchText, setPatchText] = useState("");
  const [patchFile, setPatchFile] = useState<File | null>(null);
  const [archive, setArchive] = useState<File | null>(null);
  const [coverage, setCoverage] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [ai, setAi] = useState(false);
  const [touched, setTouched] = useState(false);

  const limits = meta.data?.limits;
  const aiAvailable = Boolean(meta.data?.ai.configured && meta.data.ai.reachable !== false && meta.data.ai.model_available !== false);
  const stats = useMemo(() => patchStats(patchText), [patchText]);
  const busy = run.state.phase === "submitting" || run.state.phase === "running";

  const problems: string[] = [];
  if (mode === "paste" && !patchText.trim()) problems.push("Paste a diff to analyse.");
  if (mode === "paste" && stats && !stats.looksLikeDiff) problems.push("This does not look like a unified diff (expected lines starting with “diff --git”, “---”, or “@@”).");
  if (mode === "upload" && !patchFile) problems.push("Choose a .patch or .diff file.");
  if (limits && patchFile && patchFile.size > limits.max_patch_bytes) problems.push("The patch is over the size limit.");
  if (limits && archive && archive.size > limits.max_archive_bytes) problems.push("The repository archive is over the size limit.");
  if (limits && coverage && coverage.size > limits.max_coverage_bytes) problems.push("The coverage report is over the size limit.");

  useEffect(() => {
    if (run.state.phase !== "completed" || !run.state.analysisId) return;
    const target = `/reports/${run.state.analysisId}`;
    const timer = setTimeout(() => router.push(target), reduce ? 0 : 1600);
    return () => clearTimeout(timer);
  }, [run.state.phase, run.state.analysisId, router, reduce]);

  const submit = async () => {
    setTouched(true);
    if (problems.length) return;
    const form = new FormData();
    if (mode === "upload" && patchFile) form.set("patch", patchFile);
    else form.set("patch_text", patchText);
    if (archive) form.set("repository", archive);
    if (coverage) form.set("coverage", coverage);
    if (title.trim()) form.set("title", title.trim());
    form.set("ai", String(ai && aiAvailable));
    await run.start(() => api.createAnalysis(form));
  };

  const runSample = async (id: string) => {
    await run.start(() => api.runSample(id, { ai: ai && aiAvailable }));
  };

  return (
    <div className="mx-auto max-w-[1240px] px-4 pb-16 pt-10 sm:px-6">
      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_400px] lg:gap-14">
        <div className="min-w-0">
          <h1 className="text-[clamp(2rem,4vw,3rem)] font-[640] leading-[1.05] tracking-[-0.03em] [font-stretch:115%]">Analyse a change</h1>
          <p className="prose-lab mt-4">
            Give ChangeGuard a diff. Add the repository at its base revision to unlock cross-file checks, and a coverage report
            to measure which changed lines your tests never run. Nothing you upload is executed, and archives are processed in
            memory and discarded.
          </p>

          <div className="mt-8 space-y-7">
            <section aria-labelledby="patch-heading">
              <h2 id="patch-heading" className="mb-3 flex items-baseline gap-2 text-sm font-semibold">
                The change <span className="font-normal text-muted">required</span>
              </h2>
              <Tabs value={mode} onValueChange={(v) => setMode(v as "paste" | "upload")}>
                <TabsList>
                  <TabsTrigger value="paste">Paste a diff</TabsTrigger>
                  <TabsTrigger value="upload">Upload a patch file</TabsTrigger>
                </TabsList>
                <TabsContent value="paste" className="pt-4 outline-none">
                  <label htmlFor="patch-text" className="sr-only">
                    Unified diff
                  </label>
                  <textarea
                    id="patch-text"
                    value={patchText}
                    onChange={(e) => setPatchText(e.target.value)}
                    spellCheck={false}
                    rows={14}
                    placeholder={"diff --git a/src/pricing.py b/src/pricing.py\n--- a/src/pricing.py\n+++ b/src/pricing.py\n@@ -12,7 +12,7 @@ def apply_discount(...):\n-    if percent > 50:\n+    if percent >= 50:"}
                    className={cn(
                      "w-full resize-y rounded-[10px] border bg-surface px-3.5 py-3 font-mono text-[0.78rem] leading-[1.7] text-ink placeholder:text-faint focus:outline-none",
                      touched && mode === "paste" && problems.length ? "border-danger/60" : "border-line focus:border-ink",
                    )}
                  />
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                    {stats ? (
                      <span className="numeric">
                        {stats.files} file{stats.files === 1 ? "" : "s"} · <span className="text-ok">+{stats.additions}</span>{" "}
                        <span className="text-danger">−{stats.deletions}</span> · {stats.lines.toLocaleString()} lines ·{" "}
                        {formatBytes(new Blob([patchText]).size)}
                      </span>
                    ) : (
                      <span>
                        From your repository: <code className="font-mono text-ink-soft">git diff origin/main...HEAD</code>
                      </span>
                    )}
                    <CopyButton value="git diff origin/main...HEAD > change.patch" label="Copy command" />
                  </div>
                </TabsContent>
                <TabsContent value="upload" className="pt-4 outline-none">
                  <Dropzone
                    label="Patch file"
                    hint=".patch / .diff from git diff or git format-patch"
                    accept=".patch,.diff,.txt,text/x-diff,text/plain"
                    file={patchFile}
                    onFile={setPatchFile}
                    maxBytes={limits?.max_patch_bytes}
                  />
                </TabsContent>
              </Tabs>
            </section>

            <section aria-labelledby="context-heading" className="grid gap-5 sm:grid-cols-2">
              <h2 id="context-heading" className="sr-only">
                Optional context
              </h2>
              <div>
                <Dropzone
                  label="Repository snapshot"
                  hint=".zip or .tar.gz of the base revision"
                  accept=".zip,.tar,.tgz,.gz,.bz2,.xz,application/zip,application/gzip"
                  file={archive}
                  onFile={setArchive}
                  maxBytes={limits?.max_archive_bytes}
                  icon={<ArchiveIcon />}
                />
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  Enables callers, tests, and differential static analysis.{" "}
                  <code className="font-mono text-[0.6875rem] text-ink-soft">git archive -o base.zip origin/main</code>
                </p>
              </div>
              <div>
                <Dropzone
                  label="Coverage report"
                  hint="coverage.xml, lcov.info, or coverage.json"
                  accept=".xml,.info,.json,.lcov"
                  file={coverage}
                  onFile={setCoverage}
                  maxBytes={limits?.max_coverage_bytes}
                  icon={<GaugeIcon />}
                />
                <p className="mt-2 text-xs leading-relaxed text-muted">Must describe the head revision. Numbers are read, never computed.</p>
              </div>
            </section>

            <section className="grid gap-5 sm:grid-cols-[1fr_auto] sm:items-end">
              <div>
                <label htmlFor="title" className="mb-1.5 block text-sm font-medium">
                  Title <span className="font-normal text-muted">optional</span>
                </label>
                <input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={200}
                  placeholder="Defaults to the commit subject"
                  className="h-10 w-full rounded-md border border-line bg-bg px-3 text-sm placeholder:text-muted focus:border-ink focus:outline-none"
                />
              </div>
              <label
                className={cn(
                  "flex h-10 cursor-pointer select-none items-center gap-3 rounded-md border px-3 text-sm",
                  aiAvailable ? "border-line" : "cursor-not-allowed border-line opacity-60",
                )}
                title={aiAvailable ? undefined : meta.data?.ai.detail ?? "No AI provider configured"}
              >
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={ai && aiAvailable}
                  disabled={!aiAvailable}
                  onChange={(e) => setAi(e.target.checked)}
                />
                <span className="relative h-5 w-9 rounded-full bg-line-strong transition-colors duration-150 peer-checked:bg-ai peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-signal">
                  <span className={cn("absolute left-0.5 top-0.5 size-4 rounded-full bg-bg transition-transform duration-200 ease-[cubic-bezier(0.22,1,0.36,1)]", ai && aiAvailable && "translate-x-4")} />
                </span>
                <span>
                  <span className="text-ai" aria-hidden="true">✦</span> AI synthesis
                </span>
              </label>
            </section>
            {!aiAvailable && meta.data && (
              <p className="-mt-3 text-xs text-muted">
                AI synthesis is unavailable: {meta.data.ai.detail ?? "no provider configured"}. The report is complete without it.
              </p>
            )}

            {touched && problems.length > 0 && (
              <Notice tone="danger" title="Fix before analysing">
                <ul className="list-disc space-y-0.5 pl-4">
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </Notice>
            )}
            {run.state.phase === "failed" && run.state.error && (
              <Notice tone="danger" title="The engine rejected this input">
                {run.state.error.message}
              </Notice>
            )}

            <div className="flex flex-wrap items-center gap-4">
              <Button size="lg" onClick={submit} loading={busy} disabled={busy}>
                {busy ? "Analysing…" : "Analyse change"}
              </Button>
              {limits && (
                <span className="text-xs text-muted">
                  Up to {limits.max_patch_files} files · patch {formatBytes(limits.max_patch_bytes)} · {limits.rate_limit_per_minute} analyses/min
                </span>
              )}
            </div>
          </div>

          <section aria-labelledby="samples-heading" className="mt-14 border-t border-line pt-8">
            <h2 id="samples-heading" className="text-sm font-semibold">
              No diff at hand? Analyse a sample
            </h2>
            <p className="mt-1 text-xs text-muted">Synthetic repositories with realistic changes. Clearly labelled as sample data in their reports.</p>
            <ul className="mt-4 divide-y divide-line rounded-[10px] border border-line">
              {(samples.data ?? []).map((sample) => (
                <li key={sample.id} className="flex flex-wrap items-center gap-4 px-4 py-3.5">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{sample.title}</p>
                    <p className="mt-0.5 text-xs text-muted">{sample.tagline}</p>
                  </div>
                  <Button variant="secondary" size="sm" disabled={busy} onClick={() => runSample(sample.id)}>
                    Analyse sample
                  </Button>
                </li>
              ))}
              {samples.loading && <li className="px-4 py-3.5 text-xs text-muted">Loading samples…</li>}
              {samples.error && <li className="px-4 py-3.5 text-xs text-danger">{samples.error.message}</li>}
            </ul>
          </section>
        </div>

        <aside className="min-w-0">
          <div className="sticky top-24 rounded-[12px] border border-line p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">
                {run.state.phase === "idle" ? "What happens next" : run.state.phase === "completed" ? "Report ready" : "Pipeline"}
              </h2>
              {run.state.phase === "running" && <Pill tone="signal">Live</Pill>}
              {run.state.phase === "completed" && run.state.durationMs != null && (
                <span className="font-mono text-xs text-muted numeric">{formatDuration(run.state.durationMs)}</span>
              )}
            </div>
            {run.state.phase === "idle" ? (
              <ol className="space-y-3">
                {STAGES.map((stage, i) => (
                  <li key={stage.name} className="grid grid-cols-[20px_1fr] gap-3 text-[0.8125rem]">
                    <span className="pt-px text-right font-mono text-[0.6875rem] text-faint numeric">{String(i + 1).padStart(2, "0")}</span>
                    <span>
                      <span className="font-medium text-ink">{stage.label}</span>
                      <span className="mt-0.5 block text-xs leading-relaxed text-muted">{stage.does}</span>
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <PipelineTrack stages={run.state.stages} />
            )}
            <AnimatePresence>
              {run.state.phase === "completed" && run.state.summary && run.state.analysisId && (
                <motion.div
                  initial={reduce ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, ease: EASE }}
                  className="mt-5 border-t border-line pt-5"
                >
                  <p className="text-sm">
                    <span className="text-2xl font-[650] tracking-[-0.03em] numeric">{run.state.summary.findings_total}</span>{" "}
                    <span className="text-muted">findings · review priority </span>
                    <span className="font-semibold">{PRIORITY_META[run.state.summary.review_priority ?? "routine"]?.label}</span>
                  </p>
                  <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                    {SEVERITY_ORDER.map((s: Severity) =>
                      run.state.summary?.by_severity[s] ? (
                        <li key={s} className="flex items-center gap-1.5">
                          <SeverityMark severity={s} />
                          {run.state.summary.by_severity[s]} {SEVERITY_LABEL[s].toLowerCase()}
                        </li>
                      ) : null,
                    )}
                  </ul>
                  <ButtonLink href={`/reports/${run.state.analysisId}`} className="mt-4 w-full">
                    Open report
                  </ButtonLink>
                  <p className="mt-2 text-center text-[0.6875rem] text-faint">Opening automatically…</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </aside>
      </div>
    </div>
  );
}
