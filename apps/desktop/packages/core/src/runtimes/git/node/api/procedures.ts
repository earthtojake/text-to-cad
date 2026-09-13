import type { ContractImpl } from '@emdash/wire/rpc';
import { gitContract, type GitContract } from '#runtimes/git/api';
import { credentialOperationEnv } from '#runtimes/git/node/exec/operation-context';
import type { GitRuntime } from '#runtimes/git/node/git-runtime';
import { createCheckoutProcedures } from './checkout-procedures';
import { createRepositoryProcedures } from './repository-procedures';

export type GitProcedures = ContractImpl<GitContract>;

export function createGitProcedures(
  runtime: GitRuntime,
  contract: GitContract = gitContract
): GitProcedures {
  return {
    inspectPath: (input) => runtime.provisioning.inspectPath(input.path),
    ensureRepository: (input) => runtime.provisioning.ensureRepository(input.path, input.options),
    cloneRepository: {
      run: (input, context) =>
        runtime.provisioning.cloneRepository(input.repositoryUrl, input.targetPath, {
          signal: context.signal,
          onProgress: context.progress,
          env: credentialOperationEnv(input.credentials),
        }),
    },
    repository: {
      ...createRepositoryProcedures(runtime.repository),
      model: runtime.repository.modelHost(contract.repository.model),
    },
    checkout: {
      ...createCheckoutProcedures(runtime.checkout),
      model: runtime.checkout.modelHost(contract.checkout.model),
      content: runtime.checkout.fileContentHost(contract.checkout.content),
    },
  };
}
