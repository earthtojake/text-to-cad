import { describe, expect, it } from 'vitest';
import {
  CONTENT_SEARCH_DEFAULT_LIMIT,
  CONTENT_SEARCH_MAX_LIMIT,
  CONTENT_SEARCH_MAX_PREVIEW_LENGTH,
  FILE_SEARCH_MAX_QUERY_LENGTH,
  PATH_SEARCH_DEFAULT_LIMIT,
  PATH_SEARCH_MAX_LIMIT,
  contentSearchInputSchema,
  contentSearchProgressSchema,
  contentSearchResultSchema,
  fileSearchRootInputSchema,
  pathSearchInputSchema,
  pathSearchResultSchema,
} from './schemas';

const root = {
  root: { kind: 'posix' as const },
  segments: ['Users', 'jona', 'workspace'],
};

describe('file-search schemas', () => {
  it('uses one structured root input for registration and both search lanes', () => {
    expect(fileSearchRootInputSchema.parse({ root })).toEqual({ root });
    expect(
      pathSearchInputSchema.parse({ root, query: 'button', kinds: ['file', 'directory'] })
    ).toEqual({
      root,
      query: 'button',
      kinds: ['file', 'directory'],
    });
    expect(PATH_SEARCH_DEFAULT_LIMIT).toBe(20);
    expect(CONTENT_SEARCH_DEFAULT_LIMIT).toBe(1_000);
  });

  it('allows an empty path query and requires at least one unique entry kind', () => {
    expect(pathSearchInputSchema.parse({ root, query: '', kinds: ['file'] })).toEqual({
      root,
      query: '',
      kinds: ['file'],
    });
    expect(() => pathSearchInputSchema.parse({ root, query: 'src', kinds: [] })).toThrow();
    expect(() => pathSearchInputSchema.parse({ root, query: 'src', kinds: ['symlink'] })).toThrow();
    expect(() =>
      pathSearchInputSchema.parse({ root, query: 'src', kinds: ['file', 'file'] })
    ).toThrow();
  });

  it('bounds path queries and requested result sizes', () => {
    expect(() =>
      pathSearchInputSchema.parse({
        root,
        query: 'x'.repeat(FILE_SEARCH_MAX_QUERY_LENGTH + 1),
        kinds: ['file'],
      })
    ).toThrow();
    expect(() =>
      pathSearchInputSchema.parse({
        root,
        query: 'src',
        kinds: ['file'],
        limit: PATH_SEARCH_MAX_LIMIT + 1,
      })
    ).toThrow();
  });

  it('normalizes returned path-search entries and preserves their kinds', () => {
    expect(
      pathSearchResultSchema.parse({
        hits: [
          { path: 'src/./components/../index.ts', kind: 'file' },
          { path: 'src/./components', kind: 'directory' },
        ],
      })
    ).toEqual({
      hits: [
        { path: 'src/index.ts', kind: 'file' },
        { path: 'src/components', kind: 'directory' },
      ],
    });
  });

  it('keeps initial content-search input limited to user text, scope, and result limit', () => {
    expect(
      contentSearchInputSchema.parse({
        root,
        query: 'FILE_SEARCH_DEFAULT_LIMIT',
        under: 'packages/core',
        limit: 500,
      })
    ).toEqual({
      root,
      query: 'FILE_SEARCH_DEFAULT_LIMIT',
      under: 'packages/core',
      limit: 500,
    });

    expect(() => contentSearchInputSchema.parse({ root, query: '' })).toThrow();
    expect(() => contentSearchInputSchema.parse({ root, query: 'first\nsecond' })).toThrow();
    expect(() => contentSearchInputSchema.parse({ root, query: 'term\0suffix' })).toThrow();
    expect(() =>
      contentSearchInputSchema.parse({
        root,
        query: 'term',
        limit: CONTENT_SEARCH_MAX_LIMIT + 1,
      })
    ).toThrow();
  });

  it('accepts append-only progress batches and an authoritative terminal result', () => {
    const files = [
      {
        path: 'packages/core/src/index.ts',
        matches: [
          {
            lineNumber: 7,
            previewText: 'const value = FILE_SEARCH_DEFAULT_LIMIT;',
            locations: [
              {
                sourceRange: { startColumn: 15, endColumn: 40 },
                previewRange: { startColumn: 15, endColumn: 40 },
              },
            ],
          },
        ],
      },
    ];

    expect(contentSearchProgressSchema.parse({ files })).toEqual({ files });
    expect(contentSearchResultSchema.parse({ files, complete: true })).toEqual({
      files,
      complete: true,
    });
    expect(() =>
      contentSearchResultSchema.parse({
        files: [
          {
            ...files[0],
            matches: [
              {
                ...files[0].matches[0],
                locations: [
                  {
                    sourceRange: { startColumn: 10, endColumn: 10 },
                    previewRange: { startColumn: 10, endColumn: 10 },
                  },
                ],
              },
            ],
          },
        ],
        complete: true,
      })
    ).toThrow();
  });

  it('bounds the actual number of returned content matches', () => {
    const locations = Array.from({ length: CONTENT_SEARCH_MAX_LIMIT + 1 }, (_, index) => ({
      sourceRange: { startColumn: index + 1, endColumn: index + 2 },
      previewRange: { startColumn: index + 1, endColumn: index + 2 },
    }));

    expect(() =>
      contentSearchResultSchema.parse({
        files: [
          {
            path: 'src/index.ts',
            matches: [{ lineNumber: 1, previewText: 'x', locations }],
          },
        ],
        complete: false,
      })
    ).toThrow();
  });

  it('bounds individual previews', () => {
    expect(() =>
      contentSearchResultSchema.parse({
        files: [
          {
            path: 'src/index.ts',
            matches: [
              {
                lineNumber: 1,
                previewText: 'x'.repeat(CONTENT_SEARCH_MAX_PREVIEW_LENGTH + 1),
                locations: [
                  {
                    sourceRange: { startColumn: 1, endColumn: 2 },
                    previewRange: { startColumn: 1, endColumn: 2 },
                  },
                ],
              },
            ],
          },
        ],
        complete: false,
      })
    ).toThrow();
  });
});
