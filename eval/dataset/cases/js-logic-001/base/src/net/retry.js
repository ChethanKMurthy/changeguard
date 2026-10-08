export async function withRetry(fn, maxAttempts) {
  let attempt = 0;
  while (attempt < maxAttempts) {
    try {
      return await fn();
    } catch (err) {
      attempt += 1;
    }
  }
  throw new Error("exhausted retries");
}
