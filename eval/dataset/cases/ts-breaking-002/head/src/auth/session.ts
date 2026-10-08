export function sessionExpired(issuedAt: number, now: number): boolean {
  return now - issuedAt > 3600_000;
}
