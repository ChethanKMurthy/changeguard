import type { Metadata } from "next";

import { AnalyzeWorkspace } from "./workspace";

export const metadata: Metadata = {
  title: "Analyse a diff",
  description: "Upload or paste a git diff, optionally with a repository snapshot and a coverage report, and get an evidence-grounded risk report.",
};

export default function AnalyzePage() {
  return <AnalyzeWorkspace />;
}
