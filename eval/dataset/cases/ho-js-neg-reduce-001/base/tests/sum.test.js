import { total } from "../src/util/sum";

test("adds numbers", () => {
  expect(total([1, 2, 3])).toBe(6);
});
