export function priceLabel(cents: number, currency: string): string {
  const units = (cents / 100).toFixed(2);
  return currency === "EUR" ? `${units} €` : `$${units}`;
}
