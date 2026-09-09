import { err, ok, type Result } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import { type LiveJobContext } from '@emdash/wire/live';
import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { expose, type Query } from '@emdash/wire/state';
import type { PortableRelativePath } from '#primitives/path/api';
import {
  denormalizeDiffTarget,
  gitContract,
  type gitCheckoutContract,
  type CheckoutSelector,
  type CheckoutHeadState,
  type CheckoutStatusState,
  type GitCommandError,
  type GitFileContentKey,
  type GitLogOptions,
  type GitTransferProgress,
  type NormalizedDiffTarget,
  type PullJobInput,
  type PublishJobInput,
  type PushJobInput,
} from '#runtimes/git/api';
import type { GitAllocationGraph } from '#runtimes/git/node/allocation/allocation-graph';
import { expectedGitCommandError } from '#runtimes/git/node/api/errors';
import { credentialOperationEnv } from '#runtimes/git/node/exec/operation-context';
import type { CheckoutResource } from './checkout-resource';

type CheckoutModel = typeof gitCheckoutContract.model;
type FileContentModel = typeof gitCheckoutContract.content;
type CheckoutStateName = 'status' | 'head';

export class GitCheckoutRuntime {
  readonly model: LeasedLiveModelProvider<CheckoutModel>;
  readonly fileContentModel: LeasedLiveModelProvider<FileContentModel>;

  private readonly modelHosts = new Map<string, LeasedLiveModelProvider<CheckoutModel>>();
  private readonly fileContentHosts = new Map<string, LeasedLiveModelProvider<FileContentModel>>();

  constructor(private readonly allocations: GitAllocationGraph) {
    this.model = this.modelHost(gitContract.checkout.model);
    this.fileContentModel = this.fileContentHost(gitContract.checkout.content);
  }

  modelHost(contract: CheckoutModel = gitContract.checkout.model) {
    const existing = this.modelHosts.get(contract.id);
    if (existing) return existing;
    const host = expose(
      contract,
      {
        status: (key, scope) => this.checkoutState<CheckoutStatusState>(key, 'status', scope),
        head: (key, scope) => this.checkoutState<CheckoutHeadState>(key, 'head', scope),
      },
      {
        mutations: {
          stage: (context) => this.run(context.key, (resource) => resource.stage(context)),
          unstage: (context) => this.run(context.key, (resource) => resource.unstage(context)),
          stageAll: (context) => this.run(context.key, (resource) => resource.stageAll(context)),
          unstageAll: (context) =>
            this.run(context.key, (resource) => resource.unstageAll(context)),
          revert: (context) => this.run(context.key, (resource) => resource.revert(context)),
          revertAll: (context) => this.run(context.key, (resource) => resource.revertAll(context)),
          commit: (context) => this.run(context.key, (resource) => resource.commit(context)),
        },
      }
    );
    this.modelHosts.set(contract.id, host);
    return host;
  }

  fileContentHost(contract: FileContentModel = gitContract.checkout.content) {
    const existing = this.fileContentHosts.get(contract.id);
    if (existing) return existing;
    const host = expose(contract, {
      content: async (key, scope) => {
        const lease = this.allocations.acquireCheckout(key);
        scope.add(() => lease.release());
        const checkout = await lease.ready();
        return checkout.fileContent({ path: key.path, source: key.source }, scope);
      },
    });
    this.fileContentHosts.set(contract.id, host);
    return host;
  }

  getChangedFiles(input: CheckoutSelector & { target: NormalizedDiffTarget }) {
    return this.read(input, async (checkout) => ({
      files: await checkout.getChangedFiles(denormalizeDiffTarget(input.target)),
    }));
  }

  getFile(input: GitFileContentKey) {
    return this.run(input, (checkout) =>
      checkout.getFile({ path: input.path, source: input.source })
    );
  }

  download(input: GitFileContentKey) {
    return this.run(input, (checkout) =>
      checkout.download({ path: input.path, source: input.source })
    );
  }

  getLog(input: CheckoutSelector & { options?: GitLogOptions }) {
    return this.read(input, (checkout) => checkout.getLog(input.options));
  }

  getCommit(input: CheckoutSelector & { hash: string }) {
    return this.read(input, async (checkout) => ({ commit: await checkout.getCommit(input.hash) }));
  }

  getCommitFiles(input: CheckoutSelector & { hash: string }) {
    return this.read(input, async (checkout) => ({
      files: await checkout.getCommitFiles(input.hash),
    }));
  }

  blame(input: CheckoutSelector & { path: PortableRelativePath; ref?: string }) {
    return this.run(input, (checkout) => checkout.blame(input.path, input.ref));
  }

  push(input: PushJobInput, context: LiveJobContext<GitTransferProgress>) {
    return this.run(input, (checkout) =>
      checkout.push(input.options, {
        signal: context.signal,
        onProgress: context.progress,
        env: credentialOperationEnv(input.credentials),
      })
    );
  }

  publish(input: PublishJobInput, context: LiveJobContext<GitTransferProgress>) {
    return this.run(input, (checkout) =>
      checkout.publish(input.remote, {
        signal: context.signal,
        onProgress: context.progress,
        env: credentialOperationEnv(input.credentials),
      })
    );
  }

  pull(input: PullJobInput, context: LiveJobContext<GitTransferProgress>) {
    return this.run(input, (checkout) =>
      checkout.pull({
        signal: context.signal,
        onProgress: context.progress,
        env: credentialOperationEnv(input.credentials),
      })
    );
  }

  async dispose(): Promise<void> {
    await Promise.all([
      ...[...this.modelHosts.values()].map((host) => host.dispose()),
      ...[...this.fileContentHosts.values()].map((host) => host.dispose()),
    ]);
    this.modelHosts.clear();
    this.fileContentHosts.clear();
  }

  private read<T>(selector: CheckoutSelector, read: (resource: CheckoutResource) => Promise<T>) {
    return this.run(
      selector,
      async (resource): Promise<Result<T, never>> => ok(await read(resource))
    );
  }

  private async checkoutState<T>(
    selector: CheckoutSelector,
    name: CheckoutStateName,
    scope: Scope
  ): Promise<Query<T>> {
    const lease = this.allocations.acquireCheckout(selector);
    scope.add(() => lease.release());
    const checkout = await lease.ready();
    switch (name) {
      case 'status':
        return checkout.state('status') as unknown as Query<T>;
      case 'head':
        return checkout.state('head') as unknown as Query<T>;
    }
  }

  private async run<T, E>(
    selector: CheckoutSelector,
    run: (resource: CheckoutResource) => Promise<Result<T, E>>
  ): Promise<Result<T, E | GitCommandError>> {
    try {
      return await this.allocations.useCheckout(selector, run);
    } catch (error) {
      const expected = expectedGitCommandError(error);
      if (expected) return err(expected);
      throw error;
    }
  }
}
