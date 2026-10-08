import type { Metadata } from "next";
import Link from "next/link";

import { ReportView } from "@/components/report/report-view";
import { sampleExports, sampleReportAI } from "@/lib/static-data";

export const metadata: Metadata = {
  title: "Recorded sample report",
  description: "A recorded ChangeGuard report for the bundled synthetic billing sample, including a verified local-model note.",
};

export default function RecordedSampleReportPage() {
  const ai = sampleReportAI.ai;
  return (
    <ReportView
      report={sampleReportAI}
      exports={sampleExports}
      banner={
        <p className="mt-4 rounded-[10px] border border-line bg-surface px-4 py-3 text-[0.8125rem] leading-relaxed text-ink-soft">
          <span className="font-semibold text-ink">Recorded run.</span> The engine (v{sampleReportAI.engine_version}, ruleset{" "}
          {sampleReportAI.ruleset_version}) produced this report from the bundled synthetic sample, with AI synthesis by{" "}
          {ai.model ? <span className="font-mono text-[0.75rem]">{ai.model}</span> : "a local model"} running locally through{" "}
          {ai.provider ?? "a local provider"}. It is stored with the site so it opens without a running engine.{" "}
          <Link href="/experience" className="text-ink underline decoration-line-strong underline-offset-2 hover:decoration-signal">
            Run it live
          </Link>
          .
        </p>
      }
    />
  );
}
