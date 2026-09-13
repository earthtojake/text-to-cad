/**
 * cx.ts — dependency-free class joiner.
 *
 * Replaces `clsx` / `cn()` for the simple use case of conditionally joining
 * class names. Carries no merge or de-duplicate semantics — `@layer` ordering
 * handles precedence so tailwind-merge is unnecessary.
 *
 * Usage:
 *   cx('base', isActive && 'active', undefined, ['a', 'b'])
 *   // → 'base active a b'
 */

// Accept any value; only strings (and nested arrays of CxArgs) are emitted.
// Functions, objects, and other non-string values are silently ignored so cx()
// can be used in contexts where a className prop may be a render callback
// (e.g. @base-ui/react components pass (state) => string as className).
type CxArg = unknown;

export function cx(...args: CxArg[]): string {
  const result: string[] = [];
  for (const arg of args) {
    if (!arg) continue;
    if (typeof arg === 'string') {
      result.push(arg);
    } else if (Array.isArray(arg)) {
      const inner = cx(...arg);
      if (inner) result.push(inner);
    }
    // Functions and other non-string values are intentionally ignored.
  }
  return result.join(' ');
}
