/** Apply only keys changed from this view's baseline to the latest host record. */
export function mergeChangedRecords<T>(latest: Record<string, T>, baseline: Record<string, T>, next: Record<string, T>): Record<string, T> {
  const merged = { ...latest };
  for (const key of new Set([...Object.keys(baseline), ...Object.keys(next)])) {
    if (JSON.stringify(baseline[key]) === JSON.stringify(next[key])) continue;
    if (key in next) merged[key] = next[key]!; else delete merged[key];
  }
  return merged;
}
