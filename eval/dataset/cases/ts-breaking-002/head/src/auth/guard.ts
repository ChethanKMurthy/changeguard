import { refreshWindow, sessionExpired } from "./session";

export function shouldRefresh(issuedAt: number, now: number): boolean {
  return !sessionExpired(issuedAt, now) && now > refreshWindow(issuedAt);
}
