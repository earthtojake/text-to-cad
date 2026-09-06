import { describe, expect, it } from 'vitest';
import {
  findStructuredCloneFailure,
  formatStructuredCloneFailure,
  isStructuredCloneError,
} from './structured-clone';

describe('structured-clone diagnostics', () => {
  it('reports the path to a nested Proxy-backed array', () => {
    const labelNames = new Proxy(['bug'], {});
    const input = { filters: { labelNames } };

    expect(findStructuredCloneFailure(input, 'input')).toEqual({
      path: 'input.filters.labelNames',
      reason: 'is an Array value that cannot be structured-cloned (it may be Proxy-backed)',
    });
  });

  it('reports unsupported primitive values', () => {
    expect(formatStructuredCloneFailure({ callback: () => {} }, 'input')).toBe(
      "'input.callback' is a function, which cannot be structured-cloned"
    );
  });

  it('reports non-cloneable Map entries', () => {
    const input = new Map([['callback', () => {}]]);

    expect(findStructuredCloneFailure(input, 'input')).toEqual({
      path: 'input.<value:0>',
      reason: 'is a function, which cannot be structured-cloned',
    });
  });

  it('returns null for cloneable values, including cycles', () => {
    const input: { name: string; self?: unknown } = { name: 'cycle' };
    input.self = input;

    expect(findStructuredCloneFailure(input, 'input')).toBeNull();
  });

  it('recognizes DataCloneError across realms by name', () => {
    expect(isStructuredCloneError({ name: 'DataCloneError' })).toBe(true);
    expect(isStructuredCloneError(new Error('not cloneable'))).toBe(false);
  });
});
