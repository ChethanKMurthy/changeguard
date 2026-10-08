import { formatAmount } from "../src/pricing/currency";

test("formats dollars", () => {
  expect(formatAmount(3)).toBe("$3.00");
});
