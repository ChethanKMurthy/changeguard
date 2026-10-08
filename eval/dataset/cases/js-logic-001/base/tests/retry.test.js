import { withRetry } from "../src/net/retry";

test("returns the first success", async () => {
  await expect(withRetry(async () => 1, 3)).resolves.toBe(1);
});
