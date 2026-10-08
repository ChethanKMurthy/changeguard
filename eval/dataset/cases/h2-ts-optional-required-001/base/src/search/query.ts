export interface SearchOptions {
  limit: number;
}

export function search(term: string, options?: SearchOptions): string[] {
  const limit = options?.limit ?? 10;
  return [term].slice(0, limit);
}
