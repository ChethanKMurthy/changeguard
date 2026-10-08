import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import report from "@/data/sample-report.json";
import type { Evidence } from "@/lib/api/types";

import { EvidenceCard } from "./evidence";

const evidence = (report as unknown as { evidence: Evidence[] }).evidence;
const byType = (type: Evidence["type"]) => evidence.find((e) => e.type === type)!;

describe("EvidenceCard", () => {
  it("shows a call site's binding problems with code formatting", () => {
    const callSite = byType("call_site");
    const { container } = render(<EvidenceCard evidence={callSite} />);
    expect(screen.getByText(callSite.id)).toBeInTheDocument();
    expect(container.textContent).toContain("passes unexpected keyword argument currency");
    expect(Array.from(container.querySelectorAll("code")).map((c) => c.textContent)).toContain("currency");
    expect(screen.getByText("Resolved through an import")).toBeInTheDocument();
  });

  it("renders a signature change as removed and added lines", () => {
    const signature = byType("signature_change");
    render(<EvidenceCard evidence={signature} />);
    expect(screen.getByLabelText("Before")).toBeInTheDocument();
    expect(screen.getByLabelText("After")).toBeInTheDocument();
    expect(screen.getByText(String(signature.data.after))).toBeInTheDocument();
  });

  it("lists uncovered changed lines from the coverage report", () => {
    const coverage = evidence.find((e) => e.type === "coverage" && e.data.hits)!;
    render(<EvidenceCard evidence={coverage} />);
    const lines = screen.getAllByRole("listitem").map((li) => li.textContent);
    for (const line of Object.keys(coverage.data.hits as Record<string, number>)) expect(lines).toContain(`L${line}`);
  });
});
