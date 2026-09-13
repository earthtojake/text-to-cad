import { describe, expect, it } from 'vitest';
import { stableStringify } from './stable-stringify';

describe('stableStringify', () => {
  it('sorts object keys recursively while preserving array order', () => {
    expect(stableStringify({ b: 1, a: { d: 4, c: 3 }, list: [{ z: 2, y: 1 }] })).toBe(
      '{"a":{"c":3,"d":4},"b":1,"list":[{"y":1,"z":2}]}'
    );
  });
});
