export function evaluate(expression: string, context: Record<string, number>): boolean {
  const [left, op, right] = expression.split(" ");
  const value = context[left];
  return op === ">" ? value > Number(right) : value < Number(right);
}
