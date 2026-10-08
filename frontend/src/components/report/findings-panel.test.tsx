import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import report from "@/data/sample-report.json";
import type { Evidence, Finding } from "@/lib/api/types";

import { FindingsPanel } from "./findings-panel";

const findings = (report as unknown as { findings: Finding[] }).findings;
const evidence = new Map((report as unknown as { evidence: Evidence[] }).evidence.map((e) => [e.id, e]));

function Harness() {
  const [selected, setSelected] = useState<string | null>(null);
  return <FindingsPanel findings={findings} evidence={evidence} selectedId={selected} onSelect={setSelected} onShowInDiff={() => {}} />;
}

const shownCount = () => screen.getByText(/^Showing/).textContent;

describe("FindingsPanel", () => {
  it("filters by severity, provenance, and search, and can clear", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const filters = screen.getByRole("group", { name: "Filter findings" });
    expect(shownCount()).toBe(`Showing ${findings.length} of ${findings.length} findings`);

    const high = findings.filter((f) => f.severity === "high").length;
    await user.click(within(filters).getByRole("button", { name: /High/ }));
    expect(shownCount()).toBe(`Showing ${high} of ${findings.length} findings`);

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    const heuristic = findings.filter((f) => f.kind === "heuristic").length;
    await user.click(within(filters).getByRole("button", { name: /Heuristic/ }));
    expect(shownCount()).toBe(`Showing ${heuristic} of ${findings.length} findings`);

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await user.type(screen.getByRole("searchbox", { name: "Search findings" }), "REGIONAL_RATES");
    expect(shownCount()).toBe(`Showing 1 of ${findings.length} findings`);
  });

  it("disables the AI filter when there are no model findings", () => {
    render(<Harness />);
    const filters = screen.getByRole("group", { name: "Filter findings" });
    expect(within(filters).getByRole("button", { name: /AI-generated/ })).toBeDisabled();
  });

  it("opens the first finding with its evidence", async () => {
    render(<Harness />);
    expect(await screen.findByText(/^Evidence \(\d+\)$/)).toBeInTheDocument();
  });
});
