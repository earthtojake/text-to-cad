import { describe, expect, it } from 'vitest';
import { PALETTE_PROVIDER_CATALOG } from './palette-provider-catalog';

describe('PALETTE_PROVIDER_CATALOG', () => {
  it('contains the five native providers exactly once in stable order', () => {
    expect(
      PALETTE_PROVIDER_CATALOG.providers.map(({ kind, keyword, minQueryLength }) => ({
        kind,
        keyword,
        minQueryLength,
      }))
    ).toEqual([
      { kind: 'commands', keyword: '@commands', minQueryLength: 1 },
      { kind: 'tasks', keyword: '@tasks', minQueryLength: 1 },
      { kind: 'conversations', keyword: '@conversations', minQueryLength: 1 },
      { kind: 'files', keyword: '@files', minQueryLength: 2 },
      { kind: 'projects', keyword: '@projects', minQueryLength: 1 },
    ]);
  });
});
