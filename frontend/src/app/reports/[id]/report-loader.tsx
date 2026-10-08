"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";

import { ReportView } from "@/components/report/report-view";
import { ButtonLink } from "@/components/ui/button";
import { Notice, Skeleton } from "@/components/ui/primitives";
import { PipelineTrack } from "@/components/viz/pipeline-track";
import { api } from "@/lib/api/client";
import { useAnalysisRun } from "@/lib/use-analysis-run";
import { useResource } from "@/lib/use-resource";

export function ReportSkeleton() {
  return (
    <div className="mx-auto max-w-[1240px] px-4 pt-10 sm:px-6" aria-busy="true" aria-label="Loading report">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="mt-6 h-9 w-2/3" />
      <Skeleton className="mt-4 h-4 w-1/2" />
      <div className="mt-10 grid gap-6 lg:grid-cols-[1fr_1.15fr]">
        <div className="space-y-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
        <Skeleton className="h-[480px]" />
      </div>
    </div>
  );
}

export function ReportLoader() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { data, error, loading, reload } = useResource(`analysis:${id}`, () => api.analysis(id), { maxAgeMs: 0 });
  const run = useAnalysisRun();
  const pending = data && (data.status === "queued" || data.status === "running");

  useEffect(() => {
    if (pending && run.state.phase === "idle") run.follow(id);
  }, [pending, id, run]);

  useEffect(() => {
    if (run.state.phase === "completed" || run.state.phase === "failed") void reload();
  }, [run.state.phase, reload]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 sm:px-6">
        <Notice
          tone="danger"
          title={error.status === 404 ? "Report not found" : "Could not load this report"}
          action={<ButtonLink href="/history" variant="secondary" size="sm">All reports</ButtonLink>}
        >
          {error.status === 404 ? "It may have been deleted, or the engine was restarted with a fresh database." : error.message}
        </Notice>
      </div>
    );
  }
  if (loading && !data) return <ReportSkeleton />;
  if (!data) return null;

  if (data.status === "failed") {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 sm:px-6">
        <Notice
          tone="danger"
          title="This analysis failed"
          action={<ButtonLink href="/analyze" variant="secondary" size="sm">Try again</ButtonLink>}
        >
          {data.error?.message ?? "The engine reported an error."}
        </Notice>
      </div>
    );
  }

  if (data.status !== "completed" || !data.report) {
    return (
      <div className="mx-auto grid max-w-[1240px] gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1fr_420px]">
        <div>
          <p className="text-sm text-muted">Analysing</p>
          <h1 className="mt-2 text-3xl font-[640] tracking-[-0.025em] [font-stretch:110%]">{data.title}</h1>
          <p className="prose-lab mt-4">
            The engine is working through the pipeline. This page updates as each stage completes; the report opens when it is
            done.
          </p>
          <p className="mt-6 text-sm text-muted">
            Or go back to <Link href="/history" className="underline underline-offset-2 hover:text-ink">all reports</Link>.
          </p>
        </div>
        <div className="rounded-[12px] border border-line p-5">
          <PipelineTrack stages={run.state.stages} />
        </div>
      </div>
    );
  }

  return <ReportView analysis={data} report={data.report} />;
}
