/**
 * Serialization helpers used by the logger formatters.
 * Dependency-free; safe in both browser and Node.
 */

export function serializeLogValue(value: unknown): unknown {
  if (value instanceof Error) {
    return { name: value.name, message: value.message, stack: value.stack };
  }
  if (typeof value === 'bigint') return value.toString();
  if (typeof value === 'function') return `[Function ${value.name || 'anonymous'}]`;
  if (typeof value === 'symbol') return value.toString();
  if (value && typeof value === 'object') {
    try {
      return JSON.parse(stringifyLogValue(value));
    } catch {
      return String(value);
    }
  }
  return value;
}

export function stringifyLogValue(value: unknown): string {
  const seen = new WeakSet<object>();
  return JSON.stringify(value, (_key, nestedValue: unknown) => {
    if (nestedValue instanceof Error) return serializeLogValue(nestedValue);
    if (typeof nestedValue === 'bigint') return nestedValue.toString();
    if (typeof nestedValue === 'function')
      return `[Function ${(nestedValue as { name?: string }).name || 'anonymous'}]`;
    if (typeof nestedValue === 'symbol') return nestedValue.toString();
    if (nestedValue && typeof nestedValue === 'object') {
      if (seen.has(nestedValue)) return '[Circular]';
      seen.add(nestedValue);
    }
    return nestedValue;
  });
}

export function formatMessage(input: unknown[]): string {
  return input
    .map((value) => {
      if (typeof value === 'string') return value;
      if (value instanceof Error) return value.message;
      return stringifyLogValue(value);
    })
    .join(' ');
}
