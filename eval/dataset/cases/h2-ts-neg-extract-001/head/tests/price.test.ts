import { priceLabel } from "../src/format/price";

test("formats euros", () => {
  expect(priceLabel(1250, "EUR")).toBe("12.50 €");
});
