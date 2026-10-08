import type { UserProfile } from "../types/user";

export function emailsOf(users: UserProfile[]): string[] {
  return users.map((u) => u.email);
}
