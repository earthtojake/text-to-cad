/** `record` without `key`; the same object when it had no such key, so a store update is a no-op. */
export function withoutKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  if (!(key in record)) return record;
  const { [key]: _removed, ...rest } = record;
  return rest;
}
