import { describe, expect, it } from 'vitest';
import {
  contentSearchErrorSchema,
  fileSearchRegisterRootErrorSchema,
  pathSearchErrorSchema,
} from './errors';

const root = {
  root: { kind: 'posix' as const },
  segments: ['workspace'],
};

describe('file-search errors', () => {
  it('keeps registration failures limited to root resolution and I/O', () => {
    expect(
      fileSearchRegisterRootErrorSchema.parse({
        type: 'root-unavailable',
        root,
        reason: 'not-found',
        message: 'Workspace not found',
      })
    ).toMatchObject({ type: 'root-unavailable', reason: 'not-found' });
  });

  it('distinguishes transient path-index readiness from registration failures', () => {
    expect(
      pathSearchErrorSchema.parse({
        type: 'index-not-ready',
        root,
        message: 'Indexing is still in progress',
      })
    ).toMatchObject({ type: 'index-not-ready' });
  });

  it('does not expose engine-specific invalid-query failures for literal content search', () => {
    expect(() =>
      contentSearchErrorSchema.parse({ type: 'invalid-query', message: 'Invalid expression' })
    ).toThrow();
    expect(
      contentSearchErrorSchema.parse({
        type: 'content-search-unavailable',
        message: 'ripgrep is unavailable',
      })
    ).toMatchObject({ type: 'content-search-unavailable' });
  });
});
