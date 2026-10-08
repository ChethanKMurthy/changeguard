export function sessionExpired(issuedAt: number, now: number): boolean {
  return now - issuedAt > 3600_000;
}

export function refreshWindow(issuedAt: number): number {
  return issuedAt + 3300_000;
}
