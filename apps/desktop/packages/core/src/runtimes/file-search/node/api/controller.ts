import { createController, type Controller } from '@emdash/wire/rpc';
import { fileSearchContract, type FileSearchContract } from '#runtimes/file-search/api';
import { createFileSearchProcedures, type FileSearchRuntimeApi } from './procedures';

export type FileSearchControllerOptions = {
  contract?: FileSearchContract;
};

export function createFileSearchController(
  runtime: FileSearchRuntimeApi,
  options: FileSearchControllerOptions = {}
): Controller {
  const contract = options.contract ?? fileSearchContract;
  return createController(contract, createFileSearchProcedures(runtime));
}
