/**
 * Path utilities — pure string helpers for file paths.
 */

/** Return the last path segment, e.g. "src/foo/bar.ts" → "bar.ts". */
export function basename(path: string): string {
  return path.split('/').pop() ?? path;
}
