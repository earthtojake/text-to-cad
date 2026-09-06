import type { Result } from '@emdash/shared';
import type { ConcurrencyLimiter } from '@emdash/shared/concurrency';
import {
  CONTENT_SEARCH_DEFAULT_LIMIT,
  type ContentSearchError,
  type ContentSearchInput,
  type ContentSearchResult,
} from '#runtimes/file-search/api';
import type { RegisteredRoot } from '../root/registered-root';
import { resolveContentScope } from './content-scope';
import type { ContentSearchContext, FileContentSearcher } from './content-searcher';

export type RootContentSearchDependencies = Readonly<{
  limiter: ConcurrencyLimiter;
  searcher: FileContentSearcher;
}>;

/** Executes one root-scoped content search, cancelled when the root is unregistered. */
export function searchRootContent(
  root: RegisteredRoot,
  input: ContentSearchInput,
  context: ContentSearchContext,
  dependencies: RootContentSearchDependencies
): Promise<Result<ContentSearchResult, ContentSearchError>> {
  return root.scope
    .run('content-search', async (rootSignal) => {
      const signal = AbortSignal.any([context.signal, rootSignal]);
      const scope = await resolveContentScope(root.record.rootPath, input);
      if (!scope.success) return scope;

      return dependencies.limiter.run(signal, () =>
        dependencies.searcher.search(
          {
            ...input,
            limit: input.limit ?? CONTENT_SEARCH_DEFAULT_LIMIT,
            rootPath: scope.data.rootPath,
            searchPath: scope.data.searchPath,
          },
          { ...context, signal }
        )
      );
    })
    .value();
}
