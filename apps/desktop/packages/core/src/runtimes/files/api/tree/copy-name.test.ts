import { describe, expect, it } from 'vitest';
import { copyNameForConflict } from './copy-name';

describe('copyNameForConflict', () => {
  it('adds VS Code style copy suffixes before file extensions', () => {
    expect(copyNameForConflict('file.ts', new Set(['file.ts']))).toBe('file copy.ts');
    expect(copyNameForConflict('file.ts', new Set(['file.ts', 'file copy.ts']))).toBe(
      'file copy 2.ts'
    );
  });

  it('handles extensionless names and directories', () => {
    expect(copyNameForConflict('docs', new Set(['docs']))).toBe('docs copy');
  });

  it('treats dotfiles as extensionless names', () => {
    expect(copyNameForConflict('.env', new Set(['.env']))).toBe('.env copy');
  });
});
