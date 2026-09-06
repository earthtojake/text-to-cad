import { KeyedMutex } from '@emdash/shared/concurrency';
import type { EnvSource } from '#primitives/exec/api';
import { GitAllocationGraph } from '#runtimes/git/node/allocation/allocation-graph';
import { GitCheckoutRuntime } from '#runtimes/git/node/checkout/checkout-runtime';
import { createGitExec } from '#runtimes/git/node/exec/git-exec';
import { GitRepositoryProvisioner } from '#runtimes/git/node/repository/repository-provisioner';
import { GitRepositoryRuntime } from '#runtimes/git/node/repository/repository-runtime';
import type { BoundExec } from '#services/exec/api';
import type { IWatchService } from '#services/fs-watch/api';
import { createNativeWatchService } from '#services/fs-watch/node';

export type GitRuntimeOptions = Readonly<{
  watcher?: IWatchService;
  executable?: string;
  env?: EnvSource;
  exec?: BoundExec;
  idleTtlMs?: number;
  aliasTtlMs?: number;
  maxFileContentStates?: number;
  onError?: (context: string, error: unknown) => void;
}>;

/** Host-scoped composition root for Git provisioning and canonical resource runtimes. */
export class GitRuntime {
  readonly provisioning: GitRepositoryProvisioner;
  readonly repository: GitRepositoryRuntime;
  readonly checkout: GitCheckoutRuntime;

  private readonly allocations: GitAllocationGraph;
  private readonly watcher: IWatchService;
  private readonly ownsWatcher: boolean;
  private disposed = false;

  constructor(options: GitRuntimeOptions = {}) {
    const onError = options.onError ?? (() => {});
    this.ownsWatcher = !options.watcher;
    this.watcher = options.watcher ?? createNativeWatchService({ onError });
    const exec =
      options.exec ??
      createGitExec({
        cwd: process.cwd(),
        executable: options.executable,
        env: options.env ?? (async () => process.env),
      });
    this.provisioning = new GitRepositoryProvisioner(exec);
    this.allocations = new GitAllocationGraph({
      exec,
      watcher: this.watcher,
      objectStoreMutex: new KeyedMutex(),
      idleTtlMs: options.idleTtlMs,
      aliasTtlMs: options.aliasTtlMs,
      maxFileContentStates: options.maxFileContentStates,
      onError,
    });
    this.repository = new GitRepositoryRuntime(this.allocations);
    this.checkout = new GitCheckoutRuntime(this.allocations);
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    await Promise.all([this.repository.dispose(), this.checkout.dispose()]);
    await this.allocations.dispose();
    if (this.ownsWatcher) await this.watcher.dispose();
  }
}
