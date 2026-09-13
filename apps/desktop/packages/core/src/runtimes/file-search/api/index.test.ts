import { describe, expect, it } from 'vitest';
import * as fileSearch from './index';

describe('@emdash/core/runtimes/file-search/api public exports', () => {
  it('exports the Wire contract and portable schemas', () => {
    const exported = fileSearch as Record<string, unknown>;

    expect(exported.fileSearchContract).toBeTypeOf('object');
    expect(exported.fileSearchRootInputSchema).toBeTypeOf('object');
    expect(exported.pathSearchInputSchema).toBeTypeOf('object');
    expect(exported.pathSearchResultSchema).toBeTypeOf('object');
    expect(exported.contentSearchInputSchema).toBeTypeOf('object');
    expect(exported.contentSearchResultSchema).toBeTypeOf('object');
    expect(exported.contentSearchErrorSchema).toBeTypeOf('object');
    expect(exported.contentSearchModeSchema).toBeUndefined();
    expect(fileSearch.fileSearchContract.searchPaths.kind).toBe('procedure');
    expect(fileSearch.fileSearchContract.searchContent.kind).toBe('liveJob');
  });

  it('does not expose host runtime values', () => {
    const exported = fileSearch as Record<string, unknown>;

    expect(exported.FileSearchRuntime).toBeUndefined();
    expect(exported.PathIndexStore).toBeUndefined();
  });
});
