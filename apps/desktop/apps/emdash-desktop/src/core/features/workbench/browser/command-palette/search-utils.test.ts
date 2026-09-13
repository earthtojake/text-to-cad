import { describe, expect, it } from 'vitest';
import { getPaletteFileDisplayPath } from './search-utils';

describe('getPaletteFileDisplayPath', () => {
  it('returns a workspace-relative display path for absolute file identities', () => {
    expect(
      getPaletteFileDisplayPath({
        workspacePath: '/repo',
        filePath: '/repo/src/command-k.ts',
        fallback: '/repo/src/command-k.ts',
      })
    ).toBe('src/command-k.ts');
  });

  it('falls back to the indexed path when the workspace path is unknown', () => {
    expect(
      getPaletteFileDisplayPath({
        filePath: '/repo/src/command-k.ts',
        fallback: '/repo/src/command-k.ts',
      })
    ).toBe('/repo/src/command-k.ts');
  });
});
