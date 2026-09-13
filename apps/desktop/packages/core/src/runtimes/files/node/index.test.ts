import { describe, expect, it } from 'vitest';
import * as files from './index';

describe('@emdash/core/runtimes/files/node public exports', () => {
  it('exports only the runtime composition and controller surface', () => {
    const exported = files as Record<string, unknown>;
    expect(exported.FilesRuntime).toBeTypeOf('function');
    expect(exported.createFilesController).toBeTypeOf('function');
    expect(exported.createFilesProcedures).toBeTypeOf('function');
    expect(exported.TreeResource).toBeUndefined();
    expect(exported.RootResource).toBeUndefined();
    expect(exported.FileSystemRuntime).toBeUndefined();
  });
});
