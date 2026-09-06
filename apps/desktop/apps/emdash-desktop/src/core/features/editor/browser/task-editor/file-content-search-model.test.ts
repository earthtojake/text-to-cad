import type { ContentSearchFileResult } from '@emdash/core/runtimes/file-search/api';
import { describe, expect, it } from 'vitest';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import {
  countContentSearchOccurrences,
  mergeContentSearchFiles,
} from './file-content-search-model';

describe('file content search view model', () => {
  it('merges append-only progress batches by file', () => {
    const first = result('src/index.ts', 2, 3);
    const second = result('src/index.ts', 8, 1);
    const third = result('src/app.ts', 4, 2);

    expect(mergeContentSearchFiles([first], [second, third])).toEqual([
      { path: first.path, matches: [...first.matches, ...second.matches] },
      third,
    ]);
  });

  it('counts every occurrence, including multiple matches on one line', () => {
    expect(
      countContentSearchOccurrences([result('src/index.ts', 2, 3), result('src/app.ts', 4, 2)])
    ).toBe(5);
  });
});

function result(path: string, lineNumber: number, occurrences: number): ContentSearchFileResult {
  return {
    path: portablePath(path),
    matches: [
      {
        lineNumber,
        previewText: 'const test = true;',
        locations: Array.from({ length: occurrences }, () => ({
          sourceRange: { startColumn: 7, endColumn: 11 },
          previewRange: { startColumn: 7, endColumn: 11 },
        })),
      },
    ],
  };
}
