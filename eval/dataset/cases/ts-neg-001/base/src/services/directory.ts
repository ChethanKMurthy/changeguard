import type { UserRecord } from "../types/user";

export function emailsOf(users: UserRecord[]): string[] {
  return users.map((u) => u.email);
}
