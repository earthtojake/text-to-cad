import type { ContractImpl } from '@emdash/wire/rpc';
import type { GitContract } from '#runtimes/git/api';
import type { GitCheckoutRuntime } from '#runtimes/git/node/checkout/checkout-runtime';

type CheckoutImplementation = NonNullable<ContractImpl<GitContract>['checkout']>;

export function createCheckoutProcedures(runtime: GitCheckoutRuntime) {
  return {
    getChangedFiles: (input) => runtime.getChangedFiles(input),
    getFile: (input) => runtime.getFile(input),
    download: (input) => runtime.download(input),
    getLog: (input) => runtime.getLog(input),
    getCommit: (input) => runtime.getCommit(input),
    getCommitFiles: (input) => runtime.getCommitFiles(input),
    blame: (input) => runtime.blame(input),
    push: { run: (input, context) => runtime.push(input, context) },
    publish: { run: (input, context) => runtime.publish(input, context) },
    pull: { run: (input, context) => runtime.pull(input, context) },
  } satisfies Omit<CheckoutImplementation, 'model' | 'content'>;
}
