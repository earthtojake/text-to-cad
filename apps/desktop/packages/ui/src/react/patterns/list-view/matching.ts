// ── Types ─────────────────────────────────────────────────────────────────────

export interface TextMatcherOptions {
  /**
   * 'includes' — substring match (default, fast).
   * 'fuzzy'    — all query chars must appear in order.
   */
  mode?: 'includes' | 'fuzzy';
}

// ── Primitives ────────────────────────────────────────────────────────────────

/**
 * Returns true when `haystack` contains `query` as a case-insensitive substring.
 * An empty query always matches.
 */
export function matchesQuery(haystack: string, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return haystack.toLowerCase().includes(q);
}

/**
 * Builds a reusable item-level predicate from a field accessor.
 *
 * ```ts
 * const matchAgent = createTextMatcher((a: Agent) => [a.name, a.description]);
 * const filtered = agents.filter((a) => matchAgent(a, query));
 * ```
 */
export function createTextMatcher<T>(
  getText: (item: T) => string | string[],
  opts?: TextMatcherOptions
): (item: T, query: string) => boolean {
  const mode = opts?.mode ?? 'includes';
  return (item: T, query: string): boolean => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const raw = getText(item);
    const texts = Array.isArray(raw) ? raw : [raw];
    if (mode === 'fuzzy') {
      return texts.some((text) => fuzzyMatch(text.toLowerCase(), q));
    }
    return texts.some((text) => text.toLowerCase().includes(q));
  };
}

// ── Internal ──────────────────────────────────────────────────────────────────

/** All query chars must appear in the text in order (non-contiguous). */
function fuzzyMatch(text: string, query: string): boolean {
  let qi = 0;
  for (let ti = 0; ti < text.length && qi < query.length; ti++) {
    if (text[ti] === query[qi]) qi++;
  }
  return qi === query.length;
}
