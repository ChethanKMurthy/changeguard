import { describe, expect, it } from "vitest";

import { experienceData } from "./experience-data";

describe("experienceData", () => {
  const d = experienceData();

  it("derives figure data from the recorded report", () => {
    expect(d.recorded.findings).toBe(d.report.findings.length);
    expect(d.recorded.stages.map((s) => s.name)).toContain("references");
    expect(d.callers.incompatible.every((e) => e.type === "call_site")).toBe(true);
    expect(d.callers.incompatibleTotal).toBe(d.callers.incompatible.length);
    expect(d.coverage.executable).toBeGreaterThanOrEqual(d.coverage.covered);
  });

  it("counts every rule family, including the summed AST pattern group", () => {
    expect(d.rules.families.map((f) => f.label)).toContain("Risky call patterns");
    expect(d.rules.families.every((f) => Number.isInteger(f.count) && f.count >= 0)).toBe(true);
  });

  it("flags the recorded free-text summary only when it misattributes the condition change", () => {
    const issue = d.ai.assessmentIssue;
    if (issue) {
      expect(issue.claimed).not.toBe(issue.actual);
      expect(d.ai.assessment).toContain(`\`${issue.claimed}\``);
    }
  });
});
