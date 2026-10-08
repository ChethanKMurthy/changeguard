import { format } from "date-fns";

export function orderDate(iso: string): string {
  return format(new Date(iso), "dd MMM yyyy");
}
