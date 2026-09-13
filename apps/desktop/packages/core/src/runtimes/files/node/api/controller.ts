import { createController, type Controller } from '@emdash/wire/rpc';
import { filesContract, type FilesContract } from '#runtimes/files/api';
import type { FilesRuntime } from '#runtimes/files/node/files-runtime';
import { createFilesProcedures } from './procedures';

export type FilesControllerOptions = {
  contract?: FilesContract;
};

export function createFilesController(
  runtime: FilesRuntime,
  options: FilesControllerOptions = {}
): Controller {
  const contract = options.contract ?? filesContract;
  return createController(contract, createFilesProcedures(runtime, contract));
}
