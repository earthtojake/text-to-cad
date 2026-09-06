import { describe, expect, it } from 'vitest';
import type { PaletteProviderDef } from './provider';
import { definePaletteProviderCatalog } from './provider-catalog';

function provider(
  kind: PaletteProviderDef['kind'],
  keyword: PaletteProviderDef['keyword']
): PaletteProviderDef {
  return {
    kind,
    keyword,
    minQueryLength: 1,
    search: () => [],
    render: () => null,
  };
}

describe('definePaletteProviderCatalog', () => {
  it('rejects duplicate provider kinds and keywords', () => {
    const commands = provider('commands', '@commands');

    expect(() =>
      definePaletteProviderCatalog([commands, provider('commands', '@actions')])
    ).toThrowError('Duplicate palette provider kind: commands');
    expect(() =>
      definePaletteProviderCatalog([commands, provider('tasks', '@commands')])
    ).toThrowError('Duplicate palette provider keyword: @commands');
  });
});
