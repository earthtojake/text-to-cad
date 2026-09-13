// ── Types ─────────────────────────────────────────────────────────────────────

/** Standard two-value comparator: negative, zero, or positive. */
export type Comparator<T> = (a: T, b: T) => number;

// ── Primitive comparators ─────────────────────────────────────────────────────

/** Locale-aware string comparison. */
export const compareStrings: Comparator<string> = (a, b) => a.localeCompare(b);

/** Numeric comparison (ascending). */
export const compareNumbers: Comparator<number> = (a, b) => a - b;

/** Date comparison (ascending — earlier dates first). */
export const compareDates: Comparator<Date> = (a, b) => a.getTime() - b.getTime();

// ── Combinators ───────────────────────────────────────────────────────────────

/**
 * Derives a comparator from a field accessor, picking the right primitive
 * comparator based on the runtime type of the returned value.
 *
 * ```ts
 * sort: { keys: { name: { label: 'Name', compare: byField(a => a.name) } } }
 * ```
 */
export function byField<T>(
  get: (item: T) => string | number | Date,
  dir: 'asc' | 'desc' = 'asc'
): Comparator<T> {
  return (a, b) => {
    const av = get(a);
    const bv = get(b);
    let result: number;
    if (typeof av === 'string' && typeof bv === 'string') {
      result = compareStrings(av, bv);
    } else if (av instanceof Date && bv instanceof Date) {
      result = compareDates(av, bv);
    } else {
      result = compareNumbers(av as number, bv as number);
    }
    return dir === 'desc' ? -result : result;
  };
}

/**
 * Chains comparators left-to-right; the first non-zero result wins.
 *
 * ```ts
 * chainComparators(byField(a => a.status), byField(a => a.name))
 * ```
 */
export function chainComparators<T>(...cmps: Comparator<T>[]): Comparator<T> {
  return (a, b) => {
    for (const cmp of cmps) {
      const result = cmp(a, b);
      if (result !== 0) return result;
    }
    return 0;
  };
}
