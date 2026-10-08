/**
 * Display helpers for signature strings as the engine reports them, e.g.
 * `format_price(amount: Decimal, currency: str = "USD") -> str`.
 *
 * Used only to lay out a parameter-level picture; whether a change is breaking
 * is always the engine's verdict, never re-derived here.
 */

export interface ParsedSignature {
  prefix: string;
  params: string[];
  returns: string | null;
}

export type ParamChange = { text: string; name: string; state: "kept" | "removed" | "added" | "changed"; optional: boolean };

const OPEN = "([{";
const CLOSE = ")]}";

function splitTopLevel(source: string): string[] {
  const out: string[] = [];
  let depth = 0;
  let quote: string | null = null;
  let current = "";
  for (const ch of source) {
    if (quote) {
      current += ch;
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      current += ch;
      continue;
    }
    if (OPEN.includes(ch)) depth++;
    if (CLOSE.includes(ch)) depth--;
    if (ch === "," && depth === 0) {
      if (current.trim()) out.push(current.trim());
      current = "";
      continue;
    }
    current += ch;
  }
  if (current.trim()) out.push(current.trim());
  return out;
}

export function parseSignature(signature: string): ParsedSignature | null {
  const open = signature.indexOf("(");
  if (open === -1) return null;
  let depth = 0;
  let close = -1;
  for (let i = open; i < signature.length; i++) {
    const ch = signature[i];
    if (OPEN.includes(ch)) depth++;
    else if (CLOSE.includes(ch)) {
      depth--;
      if (depth === 0) {
        close = i;
        break;
      }
    }
  }
  if (close === -1) return null;
  const rest = signature.slice(close + 1).trim();
  return {
    prefix: signature.slice(0, open),
    params: splitTopLevel(signature.slice(open + 1, close)),
    returns: rest.startsWith("->") ? rest.slice(2).trim() : null,
  };
}

export function paramName(param: string): string {
  return param.split(/[:=]/)[0].trim();
}

/** Align parameters of two signatures by name. */
export function diffParams(before: string | null, after: string | null): ParamChange[] {
  const a = before ? parseSignature(before)?.params ?? [] : [];
  const b = after ? parseSignature(after)?.params ?? [] : [];
  const afterByName = new Map(b.map((p) => [paramName(p), p]));
  const beforeNames = new Set(a.map(paramName));
  const out: ParamChange[] = [];
  for (const p of a) {
    const name = paramName(p);
    const next = afterByName.get(name);
    if (next === undefined) out.push({ text: p, name, state: "removed", optional: p.includes("=") });
    else out.push({ text: next, name, state: next === p ? "kept" : "changed", optional: next.includes("=") });
  }
  for (const p of b) {
    const name = paramName(p);
    if (!beforeNames.has(name)) out.push({ text: p, name, state: "added", optional: p.includes("=") || name.startsWith("*") });
  }
  return out;
}
