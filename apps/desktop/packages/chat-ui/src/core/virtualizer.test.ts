/**
 * Virtualizer — unit tests.
 *
 * Covers the core BIT arithmetic plus the prepend path added for
 * incremental history loading.
 */

import { describe, expect, it } from 'vitest';
import { Virtualizer } from './virtualizer';

// ── Helpers ────────────────────────────────────────────────────────────────────

function buildVirt(heights: number[]): Virtualizer {
  const v = new Virtualizer();
  v.setCount(heights.length, (i) => heights[i]);
  // Confirm initial sizes by running setSize (simulating measured heights).
  for (let i = 0; i < heights.length; i++) {
    v.setSize(i, heights[i]);
  }
  return v;
}

// ── Basic API ─────────────────────────────────────────────────────────────────

describe('Virtualizer — basic', () => {
  it('top(0) is always 0', () => {
    const v = buildVirt([10, 20, 30]);
    expect(v.top(0)).toBe(0);
  });

  it('top(i) equals cumulative sum of rows before i', () => {
    const v = buildVirt([10, 20, 30]);
    expect(v.top(1)).toBe(10);
    expect(v.top(2)).toBe(30);
    expect(v.top(3)).toBe(60);
  });

  it('total() equals sum of all sizes', () => {
    const v = buildVirt([10, 20, 30]);
    expect(v.total()).toBe(60);
  });

  it('setSize updates top and total', () => {
    const v = buildVirt([10, 20, 30]);
    v.setSize(1, 50);
    expect(v.top(2)).toBe(60); // 10 + 50
    expect(v.total()).toBe(90);
  });

  it('findIndex locates the correct row for a pixel offset', () => {
    const v = buildVirt([10, 20, 30]);
    expect(v.findIndex(0)).toBe(0);
    expect(v.findIndex(9)).toBe(0);
    expect(v.findIndex(10)).toBe(1);
    expect(v.findIndex(29)).toBe(1);
    expect(v.findIndex(30)).toBe(2);
    expect(v.findIndex(59)).toBe(2);
  });
});

// ── prepend ────────────────────────────────────────────────────────────────────

describe('Virtualizer.prepend', () => {
  it('count and total increase correctly', () => {
    const v = buildVirt([10, 20]);
    v.prepend(2, (i) => [5, 7][i] ?? 0);
    expect(v.count).toBe(4);
    expect(v.total()).toBe(42); // 5+7+10+20
  });

  it('existing rows shift to higher indices with preserved sizes', () => {
    const v = buildVirt([10, 20, 30]);
    v.prepend(2, () => 5);
    // Rows: [5, 5, 10, 20, 30]; existing rows shifted to indices 2,3,4.
    expect(v.top(2)).toBe(10); // sum of rows 0+1 = 5+5
    expect(v.top(3)).toBe(20); // sum of rows 0+1+2 = 5+5+10
    expect(v.top(4)).toBe(40); // sum of rows 0+1+2+3 = 5+5+10+20
    expect(v.size(2)).toBe(10);
    expect(v.size(3)).toBe(20);
    expect(v.size(4)).toBe(30);
  });

  it('prepended rows have correct tops', () => {
    const v = buildVirt([100]);
    v.prepend(3, (i) => [5, 10, 15][i] ?? 0);
    expect(v.top(0)).toBe(0);
    expect(v.top(1)).toBe(5);
    expect(v.top(2)).toBe(15);
    expect(v.top(3)).toBe(30); // first original row
    expect(v.top(4)).toBe(130); // after original row (height 100)
  });

  it('setSize on a formerly-existing row (shifted index) keeps total correct', () => {
    const v = buildVirt([10, 20]);
    v.prepend(1, () => 5);
    // Original row 0 is now index 1, row 1 is now index 2.
    v.setSize(2, 50); // update former row 1 (was 20, now 50)
    expect(v.total()).toBe(5 + 10 + 50);
    expect(v.top(2)).toBe(15); // 5 + 10
  });

  it('prepend onto empty virtualizer works', () => {
    const v = new Virtualizer();
    v.prepend(3, (i) => (i + 1) * 10);
    expect(v.count).toBe(3);
    expect(v.top(0)).toBe(0);
    expect(v.top(1)).toBe(10);
    expect(v.top(2)).toBe(30);
    expect(v.total()).toBe(60);
  });

  it('multiple successive prepends compose correctly', () => {
    const v = buildVirt([100]);
    v.prepend(1, () => 10); // rows: [10, 100]
    v.prepend(1, () => 20); // rows: [20, 10, 100]
    expect(v.count).toBe(3);
    expect(v.top(1)).toBe(20);
    expect(v.top(2)).toBe(30);
    expect(v.total()).toBe(130);
  });

  it('findIndex works correctly after prepend', () => {
    const v = buildVirt([10, 20, 30]);
    v.prepend(2, () => 5); // rows: [5, 5, 10, 20, 30]
    // Tops: row0=0, row1=5, row2=10, row3=20, row4=40
    expect(v.findIndex(0)).toBe(0); // within [0,5)
    expect(v.findIndex(5)).toBe(1); // within [5,10)
    expect(v.findIndex(10)).toBe(2); // within [10,20)
    expect(v.findIndex(20)).toBe(3); // within [20,40)
    expect(v.findIndex(30)).toBe(3); // still within [20,40), not the 30px row at index 4
    expect(v.findIndex(40)).toBe(4); // within [40,70)
  });

  it('range works correctly after prepend', () => {
    const v = buildVirt([10, 10, 10]);
    v.prepend(2, () => 10); // rows: [10, 10, 10, 10, 10]; total 50
    const { start, end } = v.range(0, 25, 0, 0);
    expect(start).toBe(0);
    expect(end).toBe(2); // rows 0-2 span 30px covering the 25px viewport
  });
});
