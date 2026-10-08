export interface SearchOptions {
  limit: number;
}

export function search(term: string, options: SearchOptions): string[] {
  return [term].slice(0, options.limit);
}
