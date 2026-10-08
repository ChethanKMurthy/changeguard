import { search } from "./query";

export function suggest(prefix: string): string[] {
  return search(prefix);
}
