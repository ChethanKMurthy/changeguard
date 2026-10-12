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
  const review = name.match(/^baseline-llm-review:(.+)$/);
  if (review) return `${modelName(review[1])} reviewing alone`;
  return name;
}

/** "claude-opus-5-5" → "Claude Opus 5.5"; other model ids are shown as given. */
function modelName(id: string): string {
  const claude = id.match(/^claude-([a-z]+)-(\d+)(?:-(\d+))?$/);
  if (!claude) return id;
  const family = claude[1].charAt(0).toUpperCase() + claude[1].slice(1);
  return `Claude ${family} ${claude[2]}${claude[3] ? `.${claude[3]}` : ""}`;
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
