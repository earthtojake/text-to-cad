/**
 * Highlighter — ChatHighlighter interface + default factory.
 *
 * chat-ui defines the `ChatHighlighter` contract; consumers (emdash-desktop)
 * can inject their own implementation through ChatRootProps / MountChatOptions.
 * When no highlighter is provided, `createDefaultHighlighter()` is used, which
 * wraps a bundled Shiki singleton with the chat-ui owned em-light/em-dark themes.
 *
 * IMPORTANT — dual-theme contract: any ChatHighlighter implementation MUST call
 * Shiki (or equivalent) with `themes: { light, dark }, defaultColor: false` so
 * the token htmlStyle properties carry `--shiki-light` / `--shiki-dark` vars and
 * rootStyle carries `--shiki-light-bg` / `--shiki-dark-bg`. Code.tsx and
 * diff.module.css consume these exact var names via `.emdark:` variant classes.
 */

import bash from '@shikijs/langs/bash';
import javascript from '@shikijs/langs/javascript';
import json from '@shikijs/langs/json';
import python from '@shikijs/langs/python';
import typescript from '@shikijs/langs/typescript';
import type { ThemeRegistrationRaw } from 'shiki/core';
import { createHighlighterCoreSync } from 'shiki/core';
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript';
import { BUNDLED_DARK_THEME, BUNDLED_LIGHT_THEME } from './bundled-themes';

// ── Types ─────────────────────────────────────────────────────────────────────

/** A single token within a highlighted line. */
export type CodeToken = {
  content: string;
  /** CSS custom-property declarations, e.g. { '--shiki-light': '#..', '--shiki-dark': '#..' } */
  htmlStyle?: Record<string, string>;
};

/** Result of highlighting a code block. */
export type HighlightResult = {
  /**
   * Inline style string to set on the block wrapper to supply the background
   * CSS vars: `--shiki-light-bg` and `--shiki-dark-bg`.
   */
  rootStyle: string;
  /** Per-line token arrays. Length matches the number of `\n`-split lines. */
  lines: CodeToken[][];
};

/**
 * Syntax highlighter adapter contract owned by chat-ui.
 *
 * Implementations MUST emit the dual-theme CSS-var contract consumed by
 * Code.tsx and diff.module.css:
 *   token htmlStyle → --shiki-light / --shiki-dark
 *   rootStyle       → --shiki-light-bg / --shiki-dark-bg
 *
 * Return null for unsupported / unrecognised languages (the cache handles it
 * gracefully — the code renders un-highlighted).
 */
export interface ChatHighlighter {
  highlight(code: string, lang: string | undefined): HighlightResult | null;
}

// ── Language alias map ────────────────────────────────────────────────────────

const SUPPORTED_LANGS = new Set(['typescript', 'javascript', 'python', 'json', 'bash']);

const LANG_ALIASES: Record<string, string> = {
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  py: 'python',
  sh: 'bash',
  shell: 'bash',
  zsh: 'bash',
  jsonc: 'json',
  json5: 'json',
};

export function resolveAlias(lang: string | undefined): string | undefined {
  if (!lang) return undefined;
  const lower = lang.toLowerCase();
  return LANG_ALIASES[lower] ?? (SUPPORTED_LANGS.has(lower) ? lower : undefined);
}

// ── Default highlighter implementation ────────────────────────────────────────

type SyncHighlighter = ReturnType<typeof createHighlighterCoreSync>;
let _defaultHighlighter: SyncHighlighter | null = null;

function getDefaultShikiHighlighter(): SyncHighlighter {
  if (!_defaultHighlighter) {
    _defaultHighlighter = createHighlighterCoreSync({
      engine: createJavaScriptRegexEngine(),
      langs: [typescript, javascript, python, json, bash],
      themes: [
        BUNDLED_LIGHT_THEME as unknown as ThemeRegistrationRaw,
        BUNDLED_DARK_THEME as unknown as ThemeRegistrationRaw,
      ],
    });
  }
  return _defaultHighlighter;
}

/**
 * Tokenise `code` using the bundled Shiki singleton for the given resolved language.
 * Pure — no internal cache. Caching is handled by ChatCaches in core/caches.ts.
 */
export function computeHighlightRaw(code: string, resolvedLang: string): HighlightResult {
  const hl = getDefaultShikiHighlighter();
  const result = hl.codeToTokens(code, {
    lang: resolvedLang,
    themes: { light: 'em-light', dark: 'em-dark' },
    defaultColor: false,
  });

  const lines: CodeToken[][] = result.tokens.map((line) =>
    line.map((tok) => {
      const token: CodeToken = { content: tok.content };
      if (tok.htmlStyle && Object.keys(tok.htmlStyle).length > 0) {
        token.htmlStyle = tok.htmlStyle as Record<string, string>;
      }
      return token;
    })
  );

  const rootStyle = typeof result.bg === 'string' ? result.bg : '';
  return { rootStyle, lines };
}

/**
 * Create the default ChatHighlighter backed by the bundled em-light/em-dark
 * Shiki themes and a fixed set of common languages. Used automatically when no
 * highlighter is injected through ChatRootProps.
 *
 * For the emdash desktop app, inject a custom highlighter via the prop instead
 * so the app-singleton Shiki instance with the full language set is used.
 */
export function createDefaultHighlighter(): ChatHighlighter {
  return {
    highlight(code: string, lang: string | undefined): HighlightResult | null {
      const resolved = resolveAlias(lang);
      if (!resolved) return null;
      return computeHighlightRaw(code, resolved);
    },
  };
}
