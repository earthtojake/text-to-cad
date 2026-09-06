/**
 * Unit tests for the geometry snapshot equality helpers.
 *
 * These helpers are pure and have no DOM dependencies, so they run in the
 * `node` Vitest project without any special environment setup.
 */

import { describe, expect, it } from 'vitest';
import type { PinSnapshot } from './geometry';
import { samePin, sameRange } from './geometry';

// ── sameRange ─────────────────────────────────────────────────────────────────

describe('sameRange', () => {
  it('returns true for two empty arrays', () => {
    expect(sameRange([], [])).toBe(true);
  });

  it('returns true for identical arrays', () => {
    expect(sameRange([0, 1, 2], [0, 1, 2])).toBe(true);
  });

  it('returns false when lengths differ', () => {
    expect(sameRange([0, 1], [0, 1, 2])).toBe(false);
    expect(sameRange([0, 1, 2], [0, 1])).toBe(false);
  });

  it('returns false when an element differs', () => {
    expect(sameRange([0, 1, 2], [0, 1, 3])).toBe(false);
    expect(sameRange([0, 1, 2], [0, 2, 2])).toBe(false);
    expect(sameRange([1, 2, 3], [0, 2, 3])).toBe(false);
  });

  it('returns false for same elements in different order', () => {
    expect(sameRange([0, 1], [1, 0])).toBe(false);
  });

  it('handles single-element arrays', () => {
    expect(sameRange([5], [5])).toBe(true);
    expect(sameRange([5], [6])).toBe(false);
  });
});

// ── samePin ───────────────────────────────────────────────────────────────────

describe('samePin', () => {
  it('returns true for two nulls', () => {
    expect(samePin(null, null)).toBe(true);
  });

  it('returns false when one is null and the other is not', () => {
    const snap: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 2, overlayTop: -10 };
    expect(samePin(null, snap)).toBe(false);
    expect(samePin(snap, null)).toBe(false);
  });

  it('returns true for snapshots with identical fields', () => {
    const a: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 2, overlayTop: -10 };
    const b: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 2, overlayTop: -10 };
    expect(samePin(a, b)).toBe(true);
  });

  it('returns false when itemId differs', () => {
    const a: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 2, overlayTop: -10 };
    const b: PinSnapshot = { itemId: 'msg-2', activeUserIdx: 2, overlayTop: -10 };
    expect(samePin(a, b)).toBe(false);
  });

  it('returns false when activeUserIdx differs', () => {
    const a: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 2, overlayTop: -10 };
    const b: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 3, overlayTop: -10 };
    expect(samePin(a, b)).toBe(false);
  });

  it('returns false when overlayTop differs', () => {
    const a: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 2, overlayTop: -10 };
    const b: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 2, overlayTop: -20 };
    expect(samePin(a, b)).toBe(false);
  });

  it('returns true for overlayTop of 0 vs 0', () => {
    const a: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 0, overlayTop: 0 };
    const b: PinSnapshot = { itemId: 'msg-1', activeUserIdx: 0, overlayTop: 0 };
    expect(samePin(a, b)).toBe(true);
  });
});
