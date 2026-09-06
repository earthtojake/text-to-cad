import { err, ok, type Result } from '@emdash/shared';
import {
  PATH_SEARCH_DEFAULT_LIMIT,
  type PathSearchError,
  type PathSearchInput,
  type PathSearchResult,
} from '#runtimes/file-search/api';
import { indexNotReady, toExpectedStoreError } from '../error-mapping';
import type { RegisteredRoot } from '../root/registered-root';
import type { PathIndexStore } from './index/path-index-store';

/** Executes one synchronous path-index query against a registered root. */
export function searchRootPaths(
  root: RegisteredRoot,
  input: PathSearchInput,
  store: PathIndexStore
): Result<PathSearchResult, PathSearchError> {
  const status = root.index.status;
  switch (status.kind) {
    case 'building':
      return err(indexNotReady(input.root));
    case 'failed': {
      const failure = status.failure;
      if ('expected' in failure) return err(failure.expected);
      throw failure.unexpected;
    }
    case 'ready':
      break;
  }

  try {
    const result = store.searchPaths(
      root.record.rootKey,
      input.query,
      input.kinds,
      input.limit ?? PATH_SEARCH_DEFAULT_LIMIT
    );
    return result.kind === 'ready' ? ok({ hits: result.hits }) : err(indexNotReady(input.root));
  } catch (error) {
    const expected = toExpectedStoreError(
      input.root,
      error,
      'Unable to query the file-search index'
    );
    if (expected) return err(expected);
    throw error;
  }
}
