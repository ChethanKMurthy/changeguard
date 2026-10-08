export function charge(amount) {
  if (amount < 0) throw new Error("negative amount");
  return { amount };
}
