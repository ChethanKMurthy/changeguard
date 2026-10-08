import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import report from "@/data/sample-report.json";
import type { Report } from "@/lib/api/types";

import { FigDiff } from "./fig-diff";

const sample = report as unknown as Report;

describe("FigDiff", () => {
  it("hides the engine's markers until the reader asks for them", async () => {
    const user = userEvent.setup();
    render(<FigDiff files={sample.files} findings={sample.findings} />);
    expect(screen.queryByText(/Read them in the recorded report/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Show what ChangeGuard flagged" }));
    expect(screen.getByRole("button", { name: `Showing ${sample.findings.length} findings` })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Read them in the recorded report/)).toBeInTheDocument();
  });

  it("opens on the file with the most findings", () => {
    render(<FigDiff files={sample.files} findings={sample.findings} />);
    const counts = new Map<string, number>();
    for (const f of sample.findings) counts.set(f.location.file, (counts.get(f.location.file) ?? 0) + 1);
    const busiest = [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
    expect(screen.getByRole("button", { name: busiest.split("/").pop() })).toHaveAttribute("aria-pressed", "true");
  });
});
