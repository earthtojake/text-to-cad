import type { ContractImpl } from '@emdash/wire/rpc';
import type { FileSearchContract } from '#runtimes/file-search/api';
import type { FileSearchRuntime } from '#runtimes/file-search/node/file-search-runtime';

export type FileSearchProcedures = ContractImpl<FileSearchContract>;

export type FileSearchRuntimeApi = Pick<
  FileSearchRuntime,
  'registerRoot' | 'unregisterRoot' | 'searchPaths' | 'searchContent'
>;

export function createFileSearchProcedures(runtime: FileSearchRuntimeApi): FileSearchProcedures {
  return {
    registerRoot: (input) => runtime.registerRoot(input),
    unregisterRoot: (input) => runtime.unregisterRoot(input),
    searchPaths: (input) => runtime.searchPaths(input),
    searchContent: {
      run: (input, context) =>
        runtime.searchContent(input, {
          signal: context.signal,
          onProgress: context.progress,
        }),
    },
  };
}
