import { describe, expect, it } from 'vitest';
import { hostRef, LOCAL_HOST_REF } from '#primitives/host/api';
import {
  containsHostFileRef,
  decodeResourceUri,
  encodeResourceUri,
  hostFileRef,
  hostFileRefSchema,
  parseAbsolute,
  parsePortableRelativePath,
  relativizeHostFileRef,
  resourceKeyFromFileRef,
  resolveScopedPath,
  scopedPath,
} from './index';

describe('host file resources', () => {
  it('resolves and relativizes scoped paths', () => {
    const rootPath = parseAbsolute('/repo', { profile: { style: 'posix' } });
    const relative = parsePortableRelativePath('src/index.ts');
    expect(rootPath.success && relative.success).toBe(true);
    if (!rootPath.success || !relative.success) return;

    const root = hostFileRef(LOCAL_HOST_REF, rootPath.data);
    const scoped = scopedPath(root, relative.data);
    const resolved = resolveScopedPath(scoped);

    expect(resolved).toMatchObject({
      success: true,
      data: {
        host: LOCAL_HOST_REF,
        path: { root: { kind: 'posix' }, segments: ['repo', 'src', 'index.ts'] },
      },
    });
    if (!resolved.success) return;

    expect(containsHostFileRef(root, resolved.data)).toBe(true);
    expect(relativizeHostFileRef(root, resolved.data)).toEqual({
      success: true,
      data: 'src/index.ts',
    });
  });

  it('encodes and decodes POSIX resource URIs', () => {
    const path = parseAbsolute('/repo/a b/é.ts', { profile: { style: 'posix' } });
    expect(path.success).toBe(true);
    if (!path.success) return;

    const ref = hostFileRef(LOCAL_HOST_REF, path.data);
    const uri = encodeResourceUri(ref);

    expect(uri).toBe('emdash-file://v2/local/local/posix/repo/a%20b/%C3%A9.ts');
    expect(decodeResourceUri(uri)).toEqual({ success: true, data: ref });
  });

  it('decodes legacy v1 resource URIs', () => {
    const path = parseAbsolute('/repo/index.ts', { profile: { style: 'posix' } });
    expect(path.success).toBe(true);
    if (!path.success) return;

    expect(decodeResourceUri('emdash-file://remote-1/v1/posix/repo/index.ts')).toEqual({
      success: true,
      data: hostFileRef(hostRef('remote', 'remote-1'), path.data),
    });
  });

  it('encodes and decodes drive and UNC resource URIs', () => {
    const drive = parseAbsolute('C:/Users/David/repo', { profile: { style: 'win32' } });
    const unc = parseAbsolute('\\\\server\\share\\repo', { profile: { style: 'win32' } });
    expect(drive.success && unc.success).toBe(true);
    if (!drive.success || !unc.success) return;

    expect(decodeResourceUri(encodeResourceUri(hostFileRef(LOCAL_HOST_REF, drive.data)))).toEqual({
      success: true,
      data: hostFileRef(LOCAL_HOST_REF, drive.data),
    });
    expect(decodeResourceUri(encodeResourceUri(hostFileRef(LOCAL_HOST_REF, unc.data)))).toEqual({
      success: true,
      data: hostFileRef(LOCAL_HOST_REF, unc.data),
    });
  });

  it('rejects malformed resource URIs', () => {
    expect(decodeResourceUri('file:///repo')).toMatchObject({
      success: false,
      error: { type: 'invalid-uri' },
    });
    expect(decodeResourceUri('emdash-file://local/v1/posix/%E0%A4%A')).toMatchObject({
      success: false,
      error: { type: 'invalid-uri' },
    });
  });

  it('creates stable comparison keys without changing display spelling', () => {
    const upper = parseAbsolute('C:/Users/David/Repo.ts', { profile: { style: 'win32' } });
    const lower = parseAbsolute('c:/users/david/repo.ts', { profile: { style: 'win32' } });
    expect(upper.success && lower.success).toBe(true);
    if (!upper.success || !lower.success) return;

    const keyA = resourceKeyFromFileRef(hostFileRef(LOCAL_HOST_REF, upper.data), {
      profile: { style: 'win32' },
    });
    const keyB = resourceKeyFromFileRef(hostFileRef(LOCAL_HOST_REF, lower.data), {
      profile: { style: 'win32' },
    });
    expect(keyA).toBe(keyB);
  });

  it('validates structured refs with schemas', () => {
    const path = parseAbsolute('/repo/src/index.ts', { profile: { style: 'posix' } });
    expect(path.success).toBe(true);
    if (!path.success) return;

    expect(hostFileRefSchema.safeParse(hostFileRef(LOCAL_HOST_REF, path.data)).success).toBe(true);
    expect(
      hostFileRefSchema.safeParse({
        host: { type: 'remote', id: '' },
        path: path.data,
      }).success
    ).toBe(false);
  });
});
