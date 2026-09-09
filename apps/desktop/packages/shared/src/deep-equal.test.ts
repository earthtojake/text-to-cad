import { describe, expect, it } from 'vitest';
import { isDeepEqual } from './deep-equal';

describe('isDeepEqual', () => {
  it('compares primitives with Object.is semantics', () => {
    expect(isDeepEqual(NaN, NaN)).toBe(true);
    expect(isDeepEqual(0, -0)).toBe(false);
    expect(isDeepEqual('a', 'a')).toBe(true);
    expect(isDeepEqual('a', 'b')).toBe(false);
  });

  it('compares nested arrays and plain records independent of key insertion order', () => {
    expect(
      isDeepEqual(
        { b: [1, { y: true, x: null }], a: 'same' },
        { a: 'same', b: [1, { x: null, y: true }] }
      )
    ).toBe(true);
  });

  it('distinguishes missing keys from undefined values', () => {
    expect(isDeepEqual({ value: undefined }, {})).toBe(false);
  });

  it('rejects unsupported object instances unless they are the same reference', () => {
    const date = new Date(1);

    expect(isDeepEqual(date, date)).toBe(true);
    expect(isDeepEqual(new Date(1), new Date(1))).toBe(false);
    expect(isDeepEqual(new Map([['a', 1]]), new Map([['a', 1]]))).toBe(false);
  });
});
