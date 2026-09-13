/**
 * Lazy shiki highlighting for the Markdown component.
 *
 * Uses the generated var-based `em-syntax` theme from @emdash/theme: token
 * colors are `--em-syntax-*` CSS custom properties, so a single tokenization
 * adapts to light/dark via the theme class — no theme identity or re-highlight
 * on theme flips is needed.
 *
 * The shiki core and each grammar load lazily on first use (dynamic imports),
 * mirroring chat-ui's async/lazy highlight handling; results are kept in a
 * bounded LRU so re-renders and repeated blocks are synchronous cache hits.
 */

import * as React from 'react';
import type { HighlighterCore, LanguageRegistration, ThemeRegistrationRaw } from 'shiki/core';

export type HighlightedToken = { content: string; color?: string };
export type HighlightedLine = HighlightedToken[];

const HIGHLIGHT_CACHE_MAX = 200;

// ── Language registry ─────────────────────────────────────────────────────────

type LangLoader = () => Promise<{ default: unknown }>;

const LANG_LOADERS: Record<string, LangLoader> = {
  bash: () => import('@shikijs/langs/bash'),
  c: () => import('@shikijs/langs/c'),
  cpp: () => import('@shikijs/langs/cpp'),
  csharp: () => import('@shikijs/langs/csharp'),
  css: () => import('@shikijs/langs/css'),
  diff: () => import('@shikijs/langs/diff'),
  dockerfile: () => import('@shikijs/langs/dockerfile'),
  go: () => import('@shikijs/langs/go'),
  html: () => import('@shikijs/langs/html'),
  java: () => import('@shikijs/langs/java'),
  javascript: () => import('@shikijs/langs/javascript'),
  json: () => import('@shikijs/langs/json'),
  jsx: () => import('@shikijs/langs/jsx'),
  kotlin: () => import('@shikijs/langs/kotlin'),
  markdown: () => import('@shikijs/langs/markdown'),
  php: () => import('@shikijs/langs/php'),
  python: () => import('@shikijs/langs/python'),
  ruby: () => import('@shikijs/langs/ruby'),
  rust: () => import('@shikijs/langs/rust'),
  sql: () => import('@shikijs/langs/sql'),
  swift: () => import('@shikijs/langs/swift'),
  toml: () => import('@shikijs/langs/toml'),
  tsx: () => import('@shikijs/langs/tsx'),
  typescript: () => import('@shikijs/langs/typescript'),
  xml: () => import('@shikijs/langs/xml'),
  yaml: () => import('@shikijs/langs/yaml'),
};

const LANG_ALIASES: Record<string, string> = {
  'c++': 'cpp',
  cjs: 'javascript',
  cs: 'csharp',
  docker: 'dockerfile',
  golang: 'go',
  htm: 'html',
  js: 'javascript',
  json5: 'json',
  jsonc: 'json',
  kt: 'kotlin',
  md: 'markdown',
  mjs: 'javascript',
  py: 'python',
  rb: 'ruby',
  rs: 'rust',
  sh: 'bash',
  shell: 'bash',
  ts: 'typescript',
  yml: 'yaml',
  zsh: 'bash',
};

/** Resolve a fence language tag to a supported grammar id, or undefined. */
export function resolveHighlightLanguage(lang: string | undefined): string | undefined {
  if (!lang) return undefined;
  const lower = lang.toLowerCase();
  const resolved = LANG_ALIASES[lower] ?? lower;
  return resolved in LANG_LOADERS ? resolved : undefined;
}

// ── Lazy highlighter singleton ────────────────────────────────────────────────

let highlighterPromise: Promise<HighlighterCore> | null = null;

function getHighlighter(): Promise<HighlighterCore> {
  if (!highlighterPromise) {
    highlighterPromise = (async () => {
      const [{ createHighlighterCore }, { createJavaScriptRegexEngine }, { emSyntaxTheme }] =
        await Promise.all([
          import('shiki/core'),
          import('shiki/engine/javascript'),
          import('@emdash/theme/shiki-themes'),
        ]);
      return createHighlighterCore({
        engine: createJavaScriptRegexEngine(),
        themes: [emSyntaxTheme as unknown as ThemeRegistrationRaw],
        langs: [],
      });
    })();
  }
  return highlighterPromise;
}

// ── Bounded result cache ──────────────────────────────────────────────────────

/** `null` marks a failed highlight so it is not retried in a loop. */
const highlightCache = new Map<string, HighlightedLine[] | null>();

function cacheKey(code: string, resolvedLang: string): string {
  return `${resolvedLang}\x00${code}`;
}

function cacheSet(key: string, value: HighlightedLine[] | null): void {
  if (highlightCache.size >= HIGHLIGHT_CACHE_MAX) {
    highlightCache.delete(highlightCache.keys().next().value!);
  }
  highlightCache.set(key, value);
}

async function highlightAsync(code: string, resolvedLang: string): Promise<void> {
  const key = cacheKey(code, resolvedLang);
  try {
    const highlighter = await getHighlighter();
    if (!highlighter.getLoadedLanguages().includes(resolvedLang)) {
      const grammarModule = await LANG_LOADERS[resolvedLang]!();
      await highlighter.loadLanguage(...(grammarModule.default as LanguageRegistration[]));
    }
    const result = highlighter.codeToTokens(code, { lang: resolvedLang, theme: 'em-syntax' });
    const lines: HighlightedLine[] = result.tokens.map((line) =>
      line.map((token) =>
        token.color ? { content: token.content, color: token.color } : { content: token.content }
      )
    );
    cacheSet(key, lines);
  } catch {
    cacheSet(key, null);
  }
}

/**
 * Returns highlighted token lines for a code block, or `null` while loading /
 * for unsupported languages / after a failed highlight. Kicks off the lazy
 * highlight on first sight of a code+language pair and re-renders on arrival.
 */
export function useHighlightedCode(
  code: string,
  lang: string | undefined
): HighlightedLine[] | null {
  const resolvedLang = resolveHighlightLanguage(lang);
  const key = resolvedLang ? cacheKey(code, resolvedLang) : null;
  const cached = key ? highlightCache.get(key) : undefined;
  const [, forceRender] = React.useReducer((count: number) => count + 1, 0);

  React.useEffect(() => {
    if (!resolvedLang || cached !== undefined) return;
    let cancelled = false;
    void highlightAsync(code, resolvedLang).then(() => {
      if (!cancelled) forceRender();
    });
    return () => {
      cancelled = true;
    };
  }, [code, resolvedLang, cached]);

  return cached ?? null;
}
