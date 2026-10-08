import { describe, expect, it } from "vitest";

import { initialStages, STAGES, stageDetail, stagesFromResults } from "./stages";

describe("stageDetail", () => {
  it("pluralises rule matches", () => {
    expect(stageDetail({ name: "rules", status: "ok", notes: [], summary: { logic: { logic_changes: 1 } } })).toBe("1 rule match");
    expect(stageDetail({ name: "rules", status: "ok", notes: [], summary: { textual: { secrets: 2 }, logic: { logic_changes: 1 } } })).toBe(
      "3 rule matches",
    );
  });

  it("describes patch coverage from measured numbers", () => {
    const detail = stageDetail({
      name: "coverage",
      status: "ok",
      notes: [],
      summary: { patch_coverage_percent: 21.1, changed_covered_lines: 4, changed_executable_lines: 19 },
    });
    expect(detail).toBe("Patch coverage 21.1% · 4/19 lines");
  });

  it("uses the note for skipped stages", () => {
    expect(stageDetail({ name: "synthesis", status: "skipped", notes: ["AI disabled for this analysis"], summary: {} })).toBe(
      "AI disabled for this analysis",
    );
  });
});

describe("stagesFromResults", () => {
  it("keeps the canonical order and marks missing stages pending", () => {
    const views = stagesFromResults([{ name: "ingest", label: "Parse inputs", status: "ok", duration_ms: 1.2, summary: { files: 1 }, notes: [] }]);
    expect(views.map((v) => v.name)).toEqual(STAGES.map((s) => s.name));
    expect(views[0]).toMatchObject({ status: "ok", durationMs: 1.2 });
    expect(views.slice(1).every((v) => v.status === "pending")).toBe(true);
    expect(initialStages()).toHaveLength(STAGES.length);
  });
});
