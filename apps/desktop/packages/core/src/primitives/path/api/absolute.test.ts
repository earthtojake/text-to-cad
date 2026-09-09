import { describe, expect, it } from 'vitest';
import {
  absoluteBasename,
  absoluteDirname,
  containsAbsolute,
  formatAbsolute,
  joinAbsolute,
  parseAbsolute,
  relativeSegmentsFromAbsolute,
} from './index';

describe('absolute paths', () => {
  it('parses and formats POSIX paths without treating backslash as a separator', () => {
    const parsed = parseAbsolute('/repo/src\\literal/./index.ts', {
      profile: { style: 'posix' },
    });

    expect(parsed).toMatchObject({
      success: true,
      data: {
        root: { kind: 'posix' },
        segments: ['repo', 'src\\literal', 'index.ts'],
      },
    });
    if (!parsed.success) return;
    expect(formatAbsolute(parsed.data)).toBe('/repo/src\\literal/index.ts');
  });

  it('parses and formats Windows drive paths with explicit semantics', () => {
    const parsed = parseAbsolute('c:\\Users\\David\\repo\\file.ts', {
      profile: { style: 'win32' },
    });

    expect(parsed).toMatchObject({
      success: true,
      data: {
        root: { kind: 'drive', driveLetter: 'C' },
        segments: ['Users', 'David', 'repo', 'file.ts'],
      },
    });
    if (!parsed.success) return;
    expect(formatAbsolute(parsed.data)).toBe('C:/Users/David/repo/file.ts');
    expect(formatAbsolute(parsed.data, { separator: '\\' })).toBe(
      'C:\\Users\\David\\repo\\file.ts'
    );
  });

  it('parses and formats UNC paths under Windows semantics', () => {
    const parsed = parseAbsolute('\\\\server\\share\\dir\\file.ts', {
      profile: { style: 'win32' },
    });

    expect(parsed).toMatchObject({
      success: true,
      data: {
        root: { kind: 'unc', server: 'server', share: 'share' },
        segments: ['dir', 'file.ts'],
      },
    });
    if (!parsed.success) return;
    expect(formatAbsolute(parsed.data)).toBe('//server/share/dir/file.ts');
  });

  it('rejects incompatible absolute path styles', () => {
    expect(parseAbsolute('C:/repo', { profile: { style: 'posix' } })).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
    expect(parseAbsolute('/repo', { profile: { style: 'win32' } })).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
    expect(parseAbsolute('C:', { profile: { style: 'win32' } })).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
  });

  it('normalizes relative segments but rejects root escapes and null bytes', () => {
    expect(parseAbsolute('/repo/../other', { profile: { style: 'posix' } })).toMatchObject({
      success: true,
      data: { segments: ['other'] },
    });
    expect(parseAbsolute('/repo/../../etc', { profile: { style: 'posix' } })).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
    expect(parseAbsolute('/repo/\0bad', { profile: { style: 'posix' } })).toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
  });

  it('performs segment-boundary lexical containment', () => {
    const root = parseAbsolute('/repo', { profile: { style: 'posix' } });
    const child = parseAbsolute('/repo/src/index.ts', { profile: { style: 'posix' } });
    const sibling = parseAbsolute('/repo2/src/index.ts', { profile: { style: 'posix' } });
    expect(root.success && child.success && containsAbsolute(root.data, child.data)).toBe(true);
    expect(root.success && sibling.success && containsAbsolute(root.data, sibling.data)).toBe(
      false
    );
  });

  it('joins, finds parents, and relativizes paths', () => {
    const root = parseAbsolute('/repo', { profile: { style: 'posix' } });
    expect(root.success).toBe(true);
    if (!root.success) return;

    const joined = joinAbsolute(root.data, 'src', 'index.ts');
    expect(joined).toMatchObject({
      success: true,
      data: { segments: ['repo', 'src', 'index.ts'] },
    });
    if (!joined.success) return;

    expect(absoluteBasename(joined.data)).toBe('index.ts');
    expect(absoluteDirname(joined.data)).toMatchObject({
      root: { kind: 'posix' },
      segments: ['repo', 'src'],
    });
    expect(relativeSegmentsFromAbsolute(root.data, joined.data)).toEqual({
      success: true,
      data: ['src', 'index.ts'],
    });
  });

  it('preserves POSIX backslashes when joining tokenized path segments', () => {
    const root = parseAbsolute('/repo', { profile: { style: 'posix' } });
    expect(root.success).toBe(true);
    if (!root.success) return;

    expect(joinAbsolute(root.data, 'literal\\name')).toMatchObject({
      success: true,
      data: { segments: ['repo', 'literal\\name'] },
    });
  });
});
