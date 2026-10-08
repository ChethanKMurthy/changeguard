function toUnits(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function priceLabel(cents: number, currency: string): string {
  const units = toUnits(cents);
  return currency === "EUR" ? `${units} €` : `$${units}`;
}
