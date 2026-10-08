export function evaluate(expression: string, context: Record<string, number>): boolean {
  const fn = new Function(...Object.keys(context), `return ${expression};`);
  return Boolean(fn(...Object.values(context)));
}
