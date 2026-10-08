function stripAccents(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

export function normalizeName(value: string): string {
  return stripAccents(value).trim().toLowerCase();
}
