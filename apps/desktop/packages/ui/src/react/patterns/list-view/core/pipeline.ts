import type { ListViewSpec, FilterModel } from './types';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AsyncPipelineInputs<F extends FilterModel, K extends string> {
  query: string;
  filterModel: F | undefined;
  sortKey: K | undefined;
  sortDir: 'asc' | 'desc';
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Groups items into sections, preserving the requested key order. */
export function groupItems<T>(
  items: T[],
  by: (item: T) => string,
  order?: string[]
): Array<{ key: string; items: T[] }> {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const key = by(item);
    let bucket = map.get(key);
    if (!bucket) {
      bucket = [];
      map.set(key, bucket);
    }
    bucket.push(item);
  }

  const allKeys = [...map.keys()];
  const orderedKeys = order
    ? [...order.filter((k) => map.has(k)), ...allKeys.filter((k) => !order.includes(k))]
    : allKeys;

  return orderedKeys.map((key) => ({ key, items: map.get(key)! }));
}

// ── Sync pipeline ─────────────────────────────────────────────────────────────

/**
 * Applies sync search → filter → sort stages to `rawItems`.
 * Returns a new array; `rawItems` is not mutated.
 */
export function runSyncPipeline<T>(
  spec: ListViewSpec<T>,
  rawItems: T[],
  inputs: Pick<
    AsyncPipelineInputs<FilterModel, string>,
    'query' | 'filterModel' | 'sortKey' | 'sortDir'
  >
): T[] {
  let items = rawItems;

  // Sync search
  if (spec.search?.kind === 'sync') {
    const { query } = inputs;
    if (query.trim()) {
      const { predicate } = spec.search;
      items = items.filter((item) => predicate(item, query));
    }
  }

  // Sync filter
  if (spec.filter?.kind === 'sync' && inputs.filterModel) {
    const { apply } = spec.filter;
    const model = inputs.filterModel;
    items = items.filter((item) => apply(item, model));
  }

  // Sync sort
  if (spec.sort && !spec.sort.remote && inputs.sortKey) {
    const cmp = spec.sort.keys[inputs.sortKey]?.compare;
    if (cmp) {
      items = [...items].sort(cmp);
      if (inputs.sortDir === 'desc') items = items.slice().reverse();
    }
  }

  return items;
}

// ── Async pipeline ────────────────────────────────────────────────────────────

/**
 * Runs async stages in sequence: search → filter → sort.
 * Each stage that is `async` fires its server call; sync stages apply locally.
 * The pipeline is aborted if `signal` is already aborted between stages.
 */
export async function runAsyncPipeline<T, F extends FilterModel, K extends string>(
  spec: ListViewSpec<T>,
  rawItems: T[],
  inputs: AsyncPipelineInputs<F, K>,
  signal: AbortSignal
): Promise<T[]> {
  let items: T[] = rawItems;

  // Search stage
  if (spec.search?.kind === 'async' && inputs.query.trim()) {
    items = await spec.search.search(inputs.query, signal);
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  } else if (spec.search?.kind === 'sync' && inputs.query.trim()) {
    const { predicate } = spec.search;
    items = items.filter((item) => predicate(item, inputs.query));
  }

  // Filter stage
  if (spec.filter?.kind === 'async' && inputs.filterModel) {
    items = await spec.filter.apply(inputs.filterModel, signal);
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  } else if (spec.filter?.kind === 'sync' && inputs.filterModel) {
    const { apply } = spec.filter;
    const model = inputs.filterModel;
    items = items.filter((item) => apply(item, model));
  }

  // Sort stage
  if (spec.sort?.remote && inputs.sortKey) {
    items = await spec.sort.remote(inputs.sortKey, inputs.sortDir, signal);
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  } else if (spec.sort && inputs.sortKey) {
    const cmp = spec.sort.keys[inputs.sortKey]?.compare;
    if (cmp) {
      items = [...items].sort(cmp);
      if (inputs.sortDir === 'desc') items = items.slice().reverse();
    }
  }

  return items;
}
