/**
 * Structural preparation of log fields before serialization.
 * - Replaces Secret<T> instances with "[REDACTED]" regardless of nesting depth.
 * - Normalizes Error objects into plain objects (name, message, normalized stack).
 * - Handles circular references.
 * Dependency-free; safe in both browser and Node.
 */

import { REDACTED, isSecret } from '../secret';

const HOME_DIR_PATTERNS: Array<[RegExp, string]> = [
  [/\/Users\/[^/\s]+/g, '/Users/~'],
  [/\/home\/[^/\s]+/g, '/home/~'],
  [/([A-Z]:\\Users\\)[^\\\s]+/gi, '$1~'],
];

/** Rewrite home-directory paths to a fixed placeholder. Not a secret regex — purely deterministic. */
export function normalizePaths(s: string): string {
  return HOME_DIR_PATTERNS.reduce(
    (result, [pattern, replacement]) => result.replace(pattern, replacement),
    s
  );
}

export function serializeError(e: Error): Record<string, unknown> {
  return {
    name: e.name,
    message: e.message,
    stack: e.stack ? normalizePaths(e.stack) : undefined,
    ...(e.cause ? { cause: prepareFields(e.cause) } : {}),
  };
}

/**
 * Deep-prepare a value for structured logging:
 *   - Secret<T>  → "[REDACTED]"
 *   - Error      → serialized plain object with normalized stack
 *   - object     → recurse, detecting cycles
 *   - array      → recurse each element
 *   - primitives → pass through
 */
export function prepareFields(value: unknown, seen = new WeakSet<object>()): unknown {
  if (isSecret(value)) return REDACTED;
  if (value instanceof Error) return serializeError(value);
  if (Array.isArray(value)) return value.map((v) => prepareFields(v, seen));
  if (value && typeof value === 'object') {
    if (seen.has(value)) return '[Circular]';
    seen.add(value);
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = prepareFields(v, seen);
    }
    return out;
  }
  return value;
}
