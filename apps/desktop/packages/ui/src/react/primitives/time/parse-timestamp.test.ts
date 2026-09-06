import { afterEach, describe, expect, it, vi } from 'vitest';
import { parseTimestamp } from './parse-timestamp';
import { toCompactLabel } from './relative-time';

describe('parseTimestamp', () => {
  it('treats bare SQLite "YYYY-MM-DD HH:mm:ss" timestamps as UTC', () => {
    const date = parseTimestamp('2026-03-04 16:20:30');
    expect(date).not.toBeNull();
    expect(date!.toISOString()).toBe('2026-03-04T16:20:30.000Z');
  });

  it('does not re-suffix strings that already carry a Z timezone', () => {
    const date = parseTimestamp('2026-03-04T16:20:30Z');
    expect(date!.toISOString()).toBe('2026-03-04T16:20:30.000Z');
  });

  it('respects explicit positive UTC offsets', () => {
    const date = parseTimestamp('2026-03-04T16:20:30+02:00');
    expect(date!.toISOString()).toBe('2026-03-04T14:20:30.000Z');
  });

  it('passes through Date instances unchanged', () => {
    const input = new Date('2026-03-04T16:20:30Z');
    expect(parseTimestamp(input)).toBe(input);
  });

  it('parses epoch-millisecond numbers', () => {
    const date = parseTimestamp(Date.UTC(2026, 2, 4, 16, 20, 30));
    expect(date!.toISOString()).toBe('2026-03-04T16:20:30.000Z');
  });

  it('returns null for empty, whitespace-only, and unparseable input', () => {
    expect(parseTimestamp('')).toBeNull();
    expect(parseTimestamp('   ')).toBeNull();
    expect(parseTimestamp('not a date')).toBeNull();
    expect(parseTimestamp(Number.NaN)).toBeNull();
  });
});

describe('toCompactLabel', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows "now" for timestamps under 60 seconds old', () => {
    const now = Date.now();
    expect(toCompactLabel(new Date(now - 30_000), now)).toBe('now');
    expect(toCompactLabel(new Date(now - 59_999), now)).toBe('now');
  });

  it('abbreviates distance units', () => {
    vi.useFakeTimers();
    const now = new Date('2026-03-04T16:20:30Z');
    vi.setSystemTime(now);

    const minutesAgo = (n: number) => new Date(now.getTime() - n * 60_000);
    expect(toCompactLabel(minutesAgo(5), now.getTime())).toBe('5m');
    expect(toCompactLabel(minutesAgo(90), now.getTime())).toBe('1h');
    expect(toCompactLabel(minutesAgo(60 * 24 * 3), now.getTime())).toBe('3d');
    expect(toCompactLabel(minutesAgo(60 * 24 * 40), now.getTime())).toBe('1mo');
    expect(toCompactLabel(minutesAgo(60 * 24 * 400), now.getTime())).toBe('1y');
  });
});
