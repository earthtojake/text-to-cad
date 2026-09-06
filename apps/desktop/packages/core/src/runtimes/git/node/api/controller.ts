import { createController, type Controller } from '@emdash/wire/rpc';
import { gitContract, type GitContract } from '#runtimes/git/api';
import type { GitRuntime } from '#runtimes/git/node/git-runtime';
import { createGitProcedures } from './procedures';

export type GitControllerOptions = {
  contract?: GitContract;
};

export function createGitController(
  runtime: GitRuntime,
  options: GitControllerOptions = {}
): Controller {
  const contract = options.contract ?? gitContract;
  return createController(contract, createGitProcedures(runtime, contract));
}
