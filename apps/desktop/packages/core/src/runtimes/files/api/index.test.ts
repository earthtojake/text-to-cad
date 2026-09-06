import { describe, expect, it } from 'vitest';
import * as files from './index';

describe('@emdash/core/runtimes/files/api public exports', () => {
  it('exports the Wire contract, schemas, and pure entry helpers', () => {
    const exported = files as Record<string, unknown>;

    expect(exported.filesContract).toBeTypeOf('object');
    expect(exported.fileTreeModelSchema).toBeTypeOf('object');
    expect(exported.fileContentModelSchema).toBeTypeOf('object');
    expect(exported.isExpandableFileEntry).toBeTypeOf('function');
  });

  it('does not expose host runtime implementations', () => {
    const exported = files as Record<string, unknown>;

    expect(exported.FilesRuntime).toBeUndefined();
    expect(exported.FileSystem).toBeUndefined();
    expect(exported.createRootPathPolicy).toBeUndefined();
    expect(exported.LiveCollection).toBeUndefined();
  });
});
