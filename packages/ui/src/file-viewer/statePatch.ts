/**
 * Apply only the keys a view changed from its baseline onto the host's latest record, so a
 * stale view never overwrites another view's independent entries. Both apps merge a view's
 * `FileViewerState.renderers` into their stored record this way.
 */
export function mergeChangedRecords<T>(latest: Record<string, T>, baseline: Record<string, T>, next: Record<string, T>): Record<string, T> {
  const merged = { ...latest };
  for (const key of new Set([...Object.keys(baseline), ...Object.keys(next)])) {
    if (JSON.stringify(baseline[key]) === JSON.stringify(next[key])) continue;
    if (key in next) merged[key] = next[key]!; else delete merged[key];
  }
  return merged;
}
