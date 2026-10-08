/** Display names for evaluated systems. Unknown names fall back to the raw identifier. */
const SYSTEM_LABEL: Record<string, string> = {
  changeguard: "ChangeGuard",
  "changeguard-diff-only": "ChangeGuard, diff only",
  "baseline-keyword": "Keyword search baseline",
  "baseline-changed-symbols": "Flag-every-change baseline",
};

export function systemLabel(name: string): string {
  if (SYSTEM_LABEL[name]) return SYSTEM_LABEL[name];
  const ai = name.match(/^changeguard\+ai:(.+?)(?:@(\d+))?$/);
  if (ai) return `+ ${ai[1]}${ai[2] ? `, ${ai[2]}-sample vote` : ""}`;
  return name;
}

/** Short name for "found by" lists: the model for AI systems, the display label otherwise. */
export function shortSystemLabel(name: string): string {
  const ai = name.match(/^changeguard\+ai:(.+?)(?:@(\d+))?$/);
  if (ai) return `${ai[1]}${ai[2] ? ` (${ai[2]}-sample vote)` : ""}`;
  return systemLabel(name);
}

export function isAISystem(name: string): boolean {
  return name.startsWith("changeguard+ai:");
}

export function isBaseline(name: string): boolean {
  return name.startsWith("baseline-");
}

export const SPLIT_LABEL: Record<string, string> = {
  dev: "Dev",
  holdout: "Holdout",
  "holdout-v2": "Holdout v2",
};
