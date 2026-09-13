import { useMemo } from 'react';
import type { Comparator } from './comparators';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ClientListFilterOptions<T> {
  /** Raw query string — the hook applies `match` when non-empty. */
  query?: string;
  /** Predicate run against each item when `query` is non-empty. */
  match?: (item: T, query: string) => boolean;
  /** Additional boolean predicate applied after search. */
  filter?: (item: T) => boolean;
  /** Optional comparator — sorted result is a new array; original is unchanged. */
  sort?: Comparator<T>;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Lightweight hook for client-side search, filter, and sort over a plain array.
 * Suitable for catalog views (skills, MCP, agents, automations, prompts) where
 * state is simple enough that a full `createListView` factory is overkill.
 *
 * Returns a stable array reference (via `useMemo`) that only changes when
 * `items`, `query`, `match`, `filter`, or `sort` change.
 *
 * ```ts
 * const visible = useClientListFilter(automations, {
 *   query: search,
 *   match: createTextMatcher((a) => a.name),
 * });
 * ```
 */
export function useClientListFilter<T>(items: T[], opts: ClientListFilterOptions<T>): T[] {
  const { query, match, filter, sort } = opts;
  return useMemo(() => {
    let result = items;
    const q = query?.trim() ?? '';
    if (q && match) {
      result = result.filter((item) => match(item, q));
    }
    if (filter) {
      result = result.filter(filter);
    }
    if (sort) {
      result = [...result].sort(sort);
    }
    return result;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, query, match, filter, sort]);
}
