import { describe, expect, it } from 'vitest';
import { hostRefSchema, LOCAL_HOST_REF } from '#primitives/host/api';
import {
  absolutePathInputSchema,
  hostAbsolutePathSchema,
  hostFileRef,
  hostFileRefSchema,
  parseAbsolute,
  portableRelativePathSchema,
  resourceRefFromUriSchema,
  resourceUriSchema,
  scopedPathSchema,
} from './index';

describe('path schemas', () => {
  it('canonicalizes string inputs through parser transforms', () => {
    expect(portableRelativePathSchema.parse('src/./components/../index.ts')).toBe('src/index.ts');
    expect(hostRefSchema.parse({ type: 'remote', id: 'remote-1' })).toEqual({
      type: 'remote',
      id: 'remote-1',
    });
  });

  it('preserves parser error messages in Zod issues', () => {
    const result = portableRelativePathSchema.safeParse('../outside');

    expect(result.success).toBe(false);
    if (result.success) return;
    expect(result.error.issues[0]?.message).toBe('Path escapes its root');
  });

  it('validates native absolute path input with explicit profiles', () => {
    expect(
      absolutePathInputSchema({ profile: { style: 'posix' } }).safeParse('/repo').success
    ).toBe(true);
    expect(
      absolutePathInputSchema({ profile: { style: 'posix' } }).safeParse('C:/repo').success
    ).toBe(false);
    expect(
      absolutePathInputSchema({ profile: { style: 'win32' } }).safeParse('C:/repo').success
    ).toBe(true);
    expect(
      absolutePathInputSchema({ profile: { style: 'win32' } }).safeParse('/repo').success
    ).toBe(false);
  });

  it('rejects invalid structured path segments', () => {
    const invalidSegments = ['', '.', '..', 'a/b', 'bad\0segment'];
    for (const segment of invalidSegments) {
      expect(
        hostAbsolutePathSchema.safeParse({
          root: { kind: 'posix' },
          segments: [segment],
        }).success
      ).toBe(false);
    }
  });

  it('allows POSIX backslashes but rejects Windows structured backslashes', () => {
    expect(
      hostAbsolutePathSchema.safeParse({
        root: { kind: 'posix' },
        segments: ['literal\\name'],
      }).success
    ).toBe(true);
    expect(
      hostAbsolutePathSchema.safeParse({
        root: { kind: 'drive', driveLetter: 'C' },
        segments: ['literal\\name'],
      }).success
    ).toBe(false);
    expect(
      hostAbsolutePathSchema.safeParse({
        root: { kind: 'unc', server: 'server', share: 'share' },
        segments: ['literal\\name'],
      }).success
    ).toBe(false);
  });

  it('rejects non-canonical drive and UNC roots', () => {
    expect(
      hostAbsolutePathSchema.safeParse({
        root: { kind: 'drive', driveLetter: 'c' },
        segments: [],
      }).success
    ).toBe(false);
    expect(
      hostAbsolutePathSchema.safeParse({
        root: { kind: 'unc', server: '.', share: 'share' },
        segments: [],
      }).success
    ).toBe(false);
    expect(
      hostAbsolutePathSchema.safeParse({
        root: { kind: 'unc', server: 'server', share: 'bad/share' },
        segments: [],
      }).success
    ).toBe(false);
  });

  it('validates host refs and scoped paths through nested schemas', () => {
    const root = parseAbsolute('/repo', { profile: { style: 'posix' } });
    expect(root.success).toBe(true);
    if (!root.success) return;

    const ref = hostFileRef(LOCAL_HOST_REF, root.data);
    expect(hostFileRefSchema.safeParse(ref).success).toBe(true);
    expect(scopedPathSchema.safeParse({ root: ref, relative: 'src/./index.ts' })).toMatchObject({
      success: true,
      data: { relative: 'src/index.ts' },
    });
    expect(scopedPathSchema.safeParse({ root: ref, relative: '../outside' }).success).toBe(false);
  });

  it('separates resource URI validation from resource URI decoding', () => {
    const path = parseAbsolute('/repo/src/index.ts', { profile: { style: 'posix' } });
    expect(path.success).toBe(true);
    if (!path.success) return;

    const ref = hostFileRef(LOCAL_HOST_REF, path.data);
    const uri = 'emdash-file://local/v1/posix/repo/src/index.ts';

    expect(resourceUriSchema.parse(uri)).toBe(uri);
    expect(resourceRefFromUriSchema.parse(uri)).toEqual(ref);
    expect(resourceUriSchema.safeParse('emdash-file://local/v1/posix/%E0%A4%A').success).toBe(
      false
    );
  });
});
