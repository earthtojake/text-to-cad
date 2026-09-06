import { describe, expect, it } from 'vitest';
import {
  formatPortableRelativePath,
  joinPortableRelativePath,
  parsePortableRelativePath,
  portableRelativePathBasename,
  portableRelativePathDirname,
  portableRelativePathParts,
  ROOT_RELATIVE_PATH,
} from './index';

describe('portable relative paths', () => {
  it('normalizes dot segments and keeps the root-relative empty path', () => {
    expect(parsePortableRelativePath('')).toEqual({
      success: true,
      data: ROOT_RELATIVE_PATH,
    });
    expect(parsePortableRelativePath('.')).toEqual({
      success: true,
      data: ROOT_RELATIVE_PATH,
    });
    expect(parsePortableRelativePath('src/./components/../index.ts')).toEqual({
      success: true,
      data: 'src/index.ts',
    });
  });

  it('rejects absolute inputs and parent escapes', () => {
    expect(parsePortableRelativePath('/repo/src')).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
    expect(parsePortableRelativePath('C:/repo/src')).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
    expect(parsePortableRelativePath('../repo/src')).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
    expect(parsePortableRelativePath('a/../../b')).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
  });

  it('preserves backslash as a literal portable segment character', () => {
    expect(parsePortableRelativePath('src\\literal/file.ts')).toEqual({
      success: true,
      data: 'src\\literal/file.ts',
    });
  });

  it('supports portable path utilities', () => {
    const parsed = parsePortableRelativePath('src/components/Button.tsx');
    expect(parsed.success).toBe(true);
    if (!parsed.success) return;

    expect(formatPortableRelativePath(parsed.data)).toBe('src/components/Button.tsx');
    expect(portableRelativePathParts(parsed.data)).toEqual(['src', 'components', 'Button.tsx']);
    expect(portableRelativePathBasename(parsed.data)).toBe('Button.tsx');
    expect(portableRelativePathDirname(parsed.data)).toBe('src/components');
    expect(joinPortableRelativePath(ROOT_RELATIVE_PATH, 'src', 'index.ts')).toEqual({
      success: true,
      data: 'src/index.ts',
    });
  });
});
