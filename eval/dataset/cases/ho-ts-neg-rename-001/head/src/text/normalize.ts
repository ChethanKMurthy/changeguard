function removeDiacritics(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

export function normalizeName(value: string): string {
  return removeDiacritics(value).trim().toLowerCase();
}
