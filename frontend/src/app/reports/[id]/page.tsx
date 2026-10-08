import type { Metadata } from "next";
import { Suspense } from "react";

import { ReportLoader, ReportSkeleton } from "./report-loader";

export const metadata: Metadata = {
  title: "Report",
  description: "Findings, evidence, and the analysis trace for one code change.",
};

export default function ReportPage() {
  return (
    <Suspense fallback={<ReportSkeleton />}>
      <ReportLoader />
    </Suspense>
  );
}
