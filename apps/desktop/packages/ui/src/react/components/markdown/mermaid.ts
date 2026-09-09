/**
 * Mermaid rendering via beautiful-mermaid: synchronous source → SVG string,
 * themed with `--em-*` CSS variables so one cached SVG adapts to light/dark
 * without re-rendering (mirrors chat-ui's renderMermaid). Results are kept in
 * a bounded LRU keyed by diagram source.
 */

import { renderMermaidSVG } from 'beautiful-mermaid';

export type MermaidRenderResult =
  | { kind: 'svg'; svg: string }
  | { kind: 'error'; message: string | null };

const MERMAID_CACHE_MAX = 100;

const mermaidCache = new Map<string, MermaidRenderResult>();

function errorMessage(error: unknown): string | null {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === 'string' && error) return error;
  return null;
}

export function renderMermaid(source: string): MermaidRenderResult {
  const cached = mermaidCache.get(source);
  if (cached) {
    // LRU refresh.
    mermaidCache.delete(source);
    mermaidCache.set(source, cached);
    return cached;
  }

  let result: MermaidRenderResult;
  try {
    const svg = renderMermaidSVG(source, {
      transparent: true,
      bg: 'var(--em-background)',
      fg: 'var(--em-foreground)',
      line: 'var(--em-foreground-muted)',
      muted: 'var(--em-foreground-passive)',
      surface: 'var(--em-background-1)',
      border: 'var(--em-border)',
    });
    result = { kind: 'svg', svg };
  } catch (error) {
    result = { kind: 'error', message: errorMessage(error) };
  }

  if (mermaidCache.size >= MERMAID_CACHE_MAX) {
    mermaidCache.delete(mermaidCache.keys().next().value!);
  }
  mermaidCache.set(source, result);
  return result;
}
