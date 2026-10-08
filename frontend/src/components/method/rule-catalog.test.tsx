import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { RuleInfo } from "@/lib/api/types";

import { RuleCatalog } from "./rule-catalog";

const RULES: RuleInfo[] = [
  {
    id: "CG-API-001",
    title: "Call site incompatible with new signature",
    category: "breaking_change",
    kind: "deterministic",
    default_severity: "high",
    rationale: "A caller still uses the old calling convention.",
    languages: ["python"],
    source: "changeguard",
  },
  {
    id: "CG-LOG-001",
    title: "Condition logic changed",
    category: "logic_change",
    kind: "heuristic",
    default_severity: "medium",
    rationale: "Boundary behaviour differs.",
    languages: [],
    source: "changeguard",
  },
  {
    id: "RUFF-F821",
    title: "Undefined name",
    category: "correctness",
    kind: "deterministic",
    default_severity: "high",
    rationale: "Raises NameError when the line executes.",
    languages: ["python"],
    source: "ruff",
  },
];

describe("RuleCatalog", () => {
  it("gives every rule a stable anchor", () => {
    const { container } = render(<RuleCatalog rules={RULES} />);
    for (const rule of RULES) expect(container.querySelector(`#rule-${rule.id}`)).not.toBeNull();
  });

  it("filters by search text and by source", async () => {
    const user = userEvent.setup();
    const { container } = render(<RuleCatalog rules={RULES} />);
    await user.type(screen.getByRole("searchbox", { name: "Search rules" }), "nameerror");
    expect(container.querySelectorAll("li[id^='rule-']")).toHaveLength(1);
    expect(container.querySelector("#rule-RUFF-F821")).not.toBeNull();

    await user.clear(screen.getByRole("searchbox", { name: "Search rules" }));
    await user.click(within(screen.getByRole("group", { name: "Rule source" })).getByRole("button", { name: /ChangeGuard/ }));
    expect(container.querySelectorAll("li[id^='rule-']")).toHaveLength(2);

    await user.click(within(screen.getByRole("group", { name: "Provenance" })).getByRole("button", { name: /Heuristic/ }));
    expect(container.querySelectorAll("li[id^='rule-']")).toHaveLength(1);
    expect(screen.getByText("Condition logic changed")).toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    const user = userEvent.setup();
    render(<RuleCatalog rules={RULES} />);
    await user.type(screen.getByRole("searchbox", { name: "Search rules" }), "zzz-no-such-rule");
    expect(screen.getByText("No rule matches that search.")).toBeInTheDocument();
  });
});
