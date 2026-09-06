import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { fileKey, filesClientScope, nativeFilePath, parentFilePaths } from './runtime-client';

describe('Files runtime client paths', () => {
  it('resolves native paths to host-absolute fs keys within the scope root', () => {
    const rootPath = path.resolve('repo');
    const filePath = path.join(rootPath, 'src', 'file.ts');
    const files = filesClientScope({} as never, rootPath);

    expect(nativePathFromHost(fileKey(files, filePath).path)).toBe(filePath);
    expect(() => fileKey(files, path.resolve('outside', 'file.ts'))).toThrow();
    expect(nativeFilePath(files, 'src/file.ts' as never)).toBe(filePath);
  });

  it('expands a portable path into parent-first directory candidates', () => {
    expect(parentFilePaths('a/b/c' as never)).toEqual(['a', 'a/b', 'a/b/c']);
  });
});
