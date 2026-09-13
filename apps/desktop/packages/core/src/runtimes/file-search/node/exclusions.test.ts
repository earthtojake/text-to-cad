import { describe, expect, it } from 'vitest';
import { DefaultFileSearchExclusions } from './exclusions';
import { relativePath as relative } from './testing/paths';

describe('DefaultFileSearchExclusions', () => {
  it('excludes a configured segment at any depth without excluding similar names', () => {
    const exclusions = new DefaultFileSearchExclusions({ caseSensitive: true });

    expect(exclusions.excludes(relative('node_modules/pkg/index.js'))).toBe(true);
    expect(exclusions.excludes(relative('src/.git'))).toBe(true);
    expect(exclusions.excludes(relative('src/node_modules_backup/index.js'))).toBe(false);
    expect(exclusions.excludes(relative('src/index.ts'))).toBe(false);
    expect(exclusions.ripgrepGlobs()).toContain('!**/node_modules/**');
    expect(exclusions.watchIgnoreGlobs()).toContain('**/node_modules/**');
  });

  it('can use host-style case-insensitive segment comparisons', () => {
    const exclusions = new DefaultFileSearchExclusions({ caseSensitive: false });
    expect(exclusions.excludes(relative('SRC/NODE_MODULES/pkg/index.js'))).toBe(true);
  });
});
