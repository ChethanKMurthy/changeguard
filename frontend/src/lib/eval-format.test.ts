import { describe, expect, it } from "vitest";

import { isAISystem, isBaseline, shortSystemLabel, systemLabel } from "./eval-format";

describe("system labels", () => {
  it("names AI systems by model and vote size", () => {
    expect(systemLabel("changeguard+ai:qwen2.5-coder:7b@3")).toBe("+ qwen2.5-coder:7b, 3-sample vote");
    expect(systemLabel("changeguard+ai:llama3.2:3b")).toBe("+ llama3.2:3b");
    expect(shortSystemLabel("changeguard+ai:qwen2.5-coder:7b@3")).toBe("qwen2.5-coder:7b (3-sample vote)");
  });

  it("classifies systems", () => {
    expect(isAISystem("changeguard+ai:llama3.2:3b")).toBe(true);
    expect(isAISystem("changeguard-diff-only")).toBe(false);
    expect(isBaseline("baseline-keyword")).toBe(true);
    expect(systemLabel("something-new")).toBe("something-new");
  });
});
