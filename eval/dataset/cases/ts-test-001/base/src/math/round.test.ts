import { roundTo } from "./round";

describe("roundTo", () => {
  it("rounds to two places", () => {
    expect(roundTo(1.005, 2)).toBe(1);
  });

  it("rounds to zero places", () => {
    expect(roundTo(2.5, 0)).toBe(3);
  });
});
