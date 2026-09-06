import { describe, expect, it } from 'vitest';
import { createPathSemantics, parseAbsolute } from './index';

describe('path semantics', () => {
  it('compares paths using explicit case sensitivity', () => {
    const upper = parseAbsolute('/Repo/Src.ts', { profile: { style: 'posix' } });
    const lower = parseAbsolute('/repo/src.ts', { profile: { style: 'posix' } });
    expect(upper.success && lower.success).toBe(true);
    if (!upper.success || !lower.success) return;

    expect(createPathSemantics({ style: 'posix' }).equals(upper.data, lower.data)).toBe(false);
    expect(
      createPathSemantics({ style: 'posix', caseSensitivity: 'insensitive' }).equals(
        upper.data,
        lower.data
      )
    ).toBe(true);
  });

  it('normalizes Unicode for comparison keys when requested', () => {
    const composed = parseAbsolute('/repo/é.ts', { profile: { style: 'posix' } });
    const decomposed = parseAbsolute('/repo/e\u0301.ts', { profile: { style: 'posix' } });
    expect(composed.success && decomposed.success).toBe(true);
    if (!composed.success || !decomposed.success) return;

    const semantics = createPathSemantics({ style: 'posix', unicodeNormalization: 'nfc' });
    expect(semantics.comparisonKey(composed.data)).toBe(semantics.comparisonKey(decomposed.data));
  });

  it('checks containment through semantic comparison keys', () => {
    const root = parseAbsolute('C:/Repo', { profile: { style: 'win32' } });
    const child = parseAbsolute('c:/repo/src/index.ts', { profile: { style: 'win32' } });
    expect(root.success && child.success).toBe(true);
    if (!root.success || !child.success) return;

    expect(createPathSemantics({ style: 'win32' }).contains(root.data, child.data)).toBe(true);
  });

  it('contains descendants of filesystem roots', () => {
    const root = parseAbsolute('/', { profile: { style: 'posix' } });
    const child = parseAbsolute('/repo/index.ts', { profile: { style: 'posix' } });
    expect(root.success && child.success).toBe(true);
    if (!root.success || !child.success) return;

    expect(createPathSemantics({ style: 'posix' }).contains(root.data, child.data)).toBe(true);
  });
});
