"use client";

import type { HighlighterCore, ThemedToken } from "shiki/core";

/**
 * Syntax highlighting with Shiki, loaded lazily on the client.
 *
 * Uses the CSS-variables theme so token colours come from the design tokens
 * (and switch with light/dark automatically). Tokens are rendered as React
 * spans: untrusted repository content is never injected as HTML.
 */
let highlighter: Promise<HighlighterCore> | null = null;

const SUPPORTED = new Set(["python", "typescript", "tsx", "javascript", "jsx", "sql", "json", "toml", "yaml", "bash"]);

export function getHighlighter(): Promise<HighlighterCore> {
  highlighter ??= (async () => {
    const [{ createHighlighterCore, createCssVariablesTheme }, { createJavaScriptRegexEngine }] = await Promise.all([
      import("shiki/core"),
      import("shiki/engine/javascript"),
    ]);
    return createHighlighterCore({
      themes: [createCssVariablesTheme({ name: "changeguard", variablePrefix: "--shiki-", fontStyle: true })],
      langs: [
        import("shiki/langs/python.mjs"),
        import("shiki/langs/typescript.mjs"),
        import("shiki/langs/tsx.mjs"),
        import("shiki/langs/javascript.mjs"),
        import("shiki/langs/jsx.mjs"),
        import("shiki/langs/sql.mjs"),
        import("shiki/langs/json.mjs"),
        import("shiki/langs/toml.mjs"),
        import("shiki/langs/yaml.mjs"),
        import("shiki/langs/bash.mjs"),
      ],
      engine: createJavaScriptRegexEngine(),
    });
  })();
  return highlighter;
}

export type TokenLine = ThemedToken[];

export async function tokenize(code: string, lang: string): Promise<TokenLine[] | null> {
  if (!SUPPORTED.has(lang) || code.length > 200_000) return null;
  try {
    const hl = await getHighlighter();
    return hl.codeToTokensBase(code, { lang, theme: "changeguard" });
  } catch {
    return null;
  }
}
