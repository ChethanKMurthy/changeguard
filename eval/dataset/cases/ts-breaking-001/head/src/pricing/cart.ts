import { formatAmount } from "./currency";

export function cartLabel(total: number): string {
  return `Total: ${formatAmount(total)}`;
}
