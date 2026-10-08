import { normalizeName } from "../src/text/normalize";

test("normalizes accents and case", () => {
  expect(normalizeName("  Émile ")).toBe("emile");
});
