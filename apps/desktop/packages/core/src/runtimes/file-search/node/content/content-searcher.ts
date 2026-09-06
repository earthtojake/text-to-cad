import type { Result } from '@emdash/shared';
import type {
  ContentSearchError,
  ContentSearchInput,
  ContentSearchProgress,
  ContentSearchResult,
} from '#runtimes/file-search/api';

export type ContentSearchExecutionError = Extract<
  ContentSearchError,
  { type: 'content-search-unavailable' | 'io' }
>;

export type ResolvedContentSearchInput = Readonly<
  Omit<ContentSearchInput, 'limit'> & {
    limit: number;
    rootPath: string;
    searchPath: string;
  }
>;

export type ContentSearchContext = Readonly<{
  signal: AbortSignal;
  onProgress: (progress: ContentSearchProgress) => void;
}>;

/** Deep seam hiding content-search process execution, parsing, cancellation, and normalization. */
export interface FileContentSearcher {
  search(
    input: ResolvedContentSearchInput,
    context: ContentSearchContext
  ): Promise<Result<ContentSearchResult, ContentSearchExecutionError>>;
}
