/**
 * Parse a timestamp coming from the app's persistence or API layers.
 *
 * Bare `"YYYY-MM-DD HH:mm:ss"` strings (SQLite's default datetime format) carry
 * no timezone, and `new Date()` would interpret them as *local* time. They are
 * actually stored as UTC, so we normalize them to ISO-8601 with a `Z` suffix
 * before parsing. Dropping this silently corrupts displayed times by the local
 * UTC offset.
 *
 * Strings that already carry timezone information (`Z` or a `+hh:mm` offset)
 * are parsed as-is.
 */
export function parseTimestamp(input: string | number | Date): Date | null {
  if (input instanceof Date) return input;
  if (typeof input === 'number') {
    const d = new Date(input);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  const raw = String(input).trim();
  if (!raw) return null;

  const normalized = raw.includes('Z') || raw.includes('+') ? raw : raw.replace(' ', 'T') + 'Z';
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}
