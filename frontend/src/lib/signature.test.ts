import { describe, expect, it } from "vitest";

import { diffParams, paramName, parseSignature } from "./signature";

describe("parseSignature", () => {
  it("splits parameters at top-level commas only", () => {
    const parsed = parseSignature('format(amount: dict[str, int], sep: str = ", ", *args, **kwargs) -> tuple[str, int]');
    expect(parsed).toEqual({
      prefix: "format",
      params: ["amount: dict[str, int]", 'sep: str = ", "', "*args", "**kwargs"],
      returns: "tuple[str, int]",
    });
  });

  it("returns null when there is no parameter list", () => {
    expect(parseSignature("not a signature")).toBeNull();
  });

  it("names parameters without annotations or defaults", () => {
    expect(paramName("currency: str = 'USD'")).toBe("currency");
    expect(paramName("**kwargs")).toBe("**kwargs");
  });
});

describe("diffParams", () => {
  it("marks a removed defaulted parameter and a new required one", () => {
    const changes = diffParams('format_price(amount: Decimal, currency: str = "USD") -> str', "format_price(amount: Decimal, locale: str) -> str");
    expect(changes.map((c) => [c.name, c.state, c.optional])).toEqual([
      ["amount", "kept", false],
      ["currency", "removed", true],
      ["locale", "added", false],
    ]);
  });

  it("treats an added parameter with a default as optional", () => {
    const changes = diffParams("apply(x: int) -> int", "apply(x: int, y: int = 0) -> int");
    expect(changes.at(-1)).toMatchObject({ name: "y", state: "added", optional: true });
  });

  it("reports a changed annotation on the same name", () => {
    expect(diffParams("f(a: int)", "f(a: str)")[0]).toMatchObject({ name: "a", state: "changed" });
  });
});
