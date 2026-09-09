import { describe, expect, it, vi } from 'vitest';
import { CONTENT_SEARCH_MAX_PREVIEW_LENGTH } from '#runtimes/file-search/api';
import { relativePath as relative } from '../../testing/paths';
import {
  CONTENT_SEARCH_MAX_ACCUMULATED_PREVIEW_LENGTH,
  ContentSearchAccumulator,
} from './content-accumulator';

describe('ContentSearchAccumulator', () => {
  it('stops before aggregate preview text can exceed the runtime budget', () => {
    const accumulator = new ContentSearchAccumulator({
      signal: new AbortController().signal,
      onProgress: vi.fn(),
    });
    const previewText = 'x'.repeat(CONTENT_SEARCH_MAX_PREVIEW_LENGTH);
    const acceptedLines =
      CONTENT_SEARCH_MAX_ACCUMULATED_PREVIEW_LENGTH / CONTENT_SEARCH_MAX_PREVIEW_LENGTH;

    for (let index = 0; index < acceptedLines; index += 1) {
      expect(
        accumulator.add(
          relative('src/index.ts'),
          {
            lineNumber: index + 1,
            previewText,
            locations: [location(1, 2)],
          },
          10_000
        )
      ).toBe(false);
    }
    expect(
      accumulator.add(
        relative('src/index.ts'),
        {
          lineNumber: acceptedLines + 1,
          previewText,
          locations: [location(1, 2)],
        },
        10_000
      )
    ).toBe(true);
    expect(accumulator.result(true).files[0].matches).toHaveLength(acceptedLines);
  });

  it('does not turn an unexpected progress callback failure into a typed search error', () => {
    const bug = new Error('progress callback bug');
    const accumulator = new ContentSearchAccumulator({
      signal: new AbortController().signal,
      onProgress: () => {
        throw bug;
      },
    });
    accumulator.add(
      relative('index.ts'),
      {
        lineNumber: 1,
        previewText: 'term',
        locations: [location(1, 5)],
      },
      10
    );

    expect(() => accumulator.result(false)).toThrow(bug);
  });
});

function location(startColumn: number, endColumn: number) {
  return {
    sourceRange: { startColumn, endColumn },
    previewRange: { startColumn, endColumn },
  };
}
