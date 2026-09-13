import type { Result, Unsubscribe } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import type { BlobSource } from '@emdash/wire/rpc';
import { query, type ExposedMutationContext, type Query, type Revision } from '@emdash/wire/state';
import type { PortableRelativePath } from '#primitives/path/api';
import {
  type gitCheckoutContract,
  type BlameResult,
  type BoundGitFileContentKey,
  type CheckoutHeadState,
  type CheckoutStatusState,
  type Commit,
  type CommitFile,
  type DiffTarget,
  type DownloadError,
  type DownloadMeta,
  type GitChange,
  type GitCommandError,
  type GitLogOptions,
  type GitLogResult,
} from '#runtimes/git/api';
import type { CheckoutIdentity } from '#runtimes/git/node/allocation/identity';
import type { GitOperationContext } from '#runtimes/git/node/exec/operation-context';
import type { RepositoryResource } from '#runtimes/git/node/repository/repository-resource';
import type { WorktreeWatchEffects } from '#runtimes/git/node/repository/watch-classifier';
import { requireWatchReady, type IWatchService, type WatchHandle } from '#services/fs-watch/api';
import { GitFileContentRegistry } from './file-content-registry';
import type { GitCheckout } from './git-checkout';

const WATCH_DEBOUNCE_MS = 100;
const REVALIDATE_INTERVAL_MS = 5 * 60_000;

type CheckoutModel = typeof gitCheckoutContract.model;
type CheckoutStateName = Extract<keyof CheckoutModel['states'], string>;
type CheckoutMutationName = Extract<keyof CheckoutModel['mutations'], string>;
type CheckoutMutationContext<Name extends CheckoutMutationName> = ExposedMutationContext<
  CheckoutModel,
  Name
>;

export type CheckoutResourceOptions = Readonly<{
  identity: CheckoutIdentity;
  commands: GitCheckout;
  repository: RepositoryResource;
  watcher: IWatchService;
  onError?: (context: string, error: unknown) => void;
  maxFileContentStates?: number;
}>;

/** One canonical checkout, including commands, live state, ordering, and reconciliation. */
export class CheckoutResource {
  readonly identity: CheckoutIdentity;
  readonly repository: RepositoryResource;

  private readonly commands: GitCheckout;
  private readonly statesScope = createScope({ label: 'git-checkout-states' });
  private readonly states: {
    status: Query<CheckoutStatusState>;
    head: Query<CheckoutHeadState>;
  };
  private readonly fileContents: GitFileContentRegistry;
  private readonly worktreeWatch: WatchHandle;
  private readonly unregister: Unsubscribe;
  private readonly onError: (context: string, error: unknown) => void;
  private disposed = false;

  static async create(options: CheckoutResourceOptions): Promise<CheckoutResource> {
    const resource = new CheckoutResource(options);
    try {
      await requireWatchReady(resource.worktreeWatch);
      return resource;
    } catch (error) {
      await resource.dispose();
      throw error;
    }
  }

  private constructor(options: CheckoutResourceOptions) {
    this.identity = options.identity;
    this.commands = options.commands;
    this.repository = options.repository;
    this.onError = options.onError ?? (() => {});
    this.states = {
      status: this.computed('status', () => this.commands.getStatus()),
      head: this.computed('head', () => this.commands.getHead()),
    };
    this.fileContents = new GitFileContentRegistry({
      commands: this.commands,
      execute: (run) => this.repository.execute(run),
      maxEntries: options.maxFileContentStates,
      onError: this.onError,
    });
    this.worktreeWatch = options.watcher.watch(
      this.identity.checkoutRoot,
      (events) => this.onWorktreeEvents(events),
      {
        ignore: ['.git/**'],
        onResync: () => this.onWorktreeResync(),
      }
    );
    this.unregister = this.repository.registerCheckout(this);
  }

  state(name: 'status'): Query<CheckoutStatusState>;
  state(name: 'head'): Query<CheckoutHeadState>;
  state(name: CheckoutStateName) {
    return this.states[name];
  }

  refresh(name: CheckoutStateName, mutationId?: string): Promise<Revision> {
    return this.states[name].refresh({ mutationIds: mutationId ? [mutationId] : undefined });
  }

  invalidate(name: CheckoutStateName): void {
    this.states[name].invalidate();
  }

  fileContent(key: BoundGitFileContentKey, scope: Scope) {
    this.assertActive();
    return this.fileContents.state(key, scope);
  }

  getChangedFiles(target: DiffTarget): Promise<GitChange[]> {
    this.assertActive();
    return this.commands.getChangedFiles(target);
  }

  getFile(
    key: BoundGitFileContentKey
  ): Promise<Result<{ content: string | null }, GitCommandError>> {
    this.assertActive();
    return this.commands.getFile(key);
  }

  download(
    key: BoundGitFileContentKey
  ): Promise<Result<{ meta: DownloadMeta; source: BlobSource }, DownloadError>> {
    this.assertActive();
    return this.commands.download(key);
  }

  getLog(options?: GitLogOptions): Promise<GitLogResult> {
    this.assertActive();
    return this.commands.getLog(options);
  }

  getCommit(hash: string): Promise<Commit | null> {
    this.assertActive();
    return this.commands.getCommit(hash);
  }

  getCommitFiles(hash: string): Promise<CommitFile[]> {
    this.assertActive();
    return this.commands.getCommitFiles(hash);
  }

  blame(filePath: string, ref?: string): Promise<Result<BlameResult, GitCommandError>> {
    this.assertActive();
    return this.commands.blame(filePath, ref);
  }

  async stage(context: CheckoutMutationContext<'stage'>) {
    const result = await this.execute(() => this.commands.stage(context.input.paths));
    if (result.success) await this.settleIndexChange(context, context.input.paths);
    return result;
  }

  async unstage(context: CheckoutMutationContext<'unstage'>) {
    const result = await this.execute(() => this.commands.unstage(context.input.paths));
    if (result.success) await this.settleIndexChange(context, context.input.paths);
    return result;
  }

  async stageAll(context: CheckoutMutationContext<'stageAll'>) {
    const result = await this.execute(() => this.commands.stageAll());
    if (result.success) await this.settleIndexChange(context, 'all');
    return result;
  }

  async unstageAll(context: CheckoutMutationContext<'unstageAll'>) {
    const result = await this.execute(() => this.commands.unstageAll());
    if (result.success) await this.settleIndexChange(context, 'all');
    return result;
  }

  async revert(context: CheckoutMutationContext<'revert'>) {
    const result = await this.execute(() => this.commands.revert(context.input.paths));
    if (result.success) this.contentChanged();
    return result;
  }

  async revertAll(_context: CheckoutMutationContext<'revertAll'>) {
    const result = await this.execute(() => this.commands.revertAll());
    if (result.success) this.contentChanged();
    return result;
  }

  async commit(context: CheckoutMutationContext<'commit'>) {
    const result = await this.execute(() =>
      this.commands.commit(context.input.message, context.input.options)
    );
    this.historyChanged(result.success);
    return result;
  }

  async push(options: Parameters<GitCheckout['push']>[0], context: GitOperationContext) {
    const result = await this.execute(() => this.commands.push(options, context));
    if (result.success) {
      await this.refresh('head');
      this.repository.invalidate('refs');
    }
    return result;
  }

  async publish(remote: string, context: GitOperationContext) {
    const result = await this.execute(() => this.commands.publish(remote, context));
    if (result.success) {
      await this.refresh('head');
      this.repository.invalidate('refs');
    }
    return result;
  }

  async pull(context: GitOperationContext) {
    const result = await this.execute(() => this.commands.pull(context), true);
    this.syncChanged();
    return result;
  }

  invalidateRepositoryHistory(): void {
    this.invalidate('status');
    this.invalidate('head');
    this.fileContents.invalidate('all', 'refs');
  }

  applyRepositoryWatchEffects(effects: WorktreeWatchEffects): void {
    if (effects.status) this.invalidate('status');
    if (effects.head) this.invalidate('head');
    if (effects.head) this.fileContents.invalidate('all', 'refs');
    if (effects.status) this.fileContents.invalidate('all', 'index');
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.unregister();
    await this.worktreeWatch.release();
    await this.statesScope.dispose();
    this.fileContents.dispose();
  }

  private execute<T>(run: () => Promise<T>, objectTransfer = false): Promise<T> {
    this.assertActive();
    return this.repository.execute(run, objectTransfer);
  }

  private async settleIndexChange(
    context:
      | CheckoutMutationContext<'stage'>
      | CheckoutMutationContext<'unstage'>
      | CheckoutMutationContext<'stageAll'>
      | CheckoutMutationContext<'unstageAll'>,
    paths: 'all' | readonly PortableRelativePath[]
  ): Promise<void> {
    await context.observed('status', this.refresh('status', context.mutationId));
    this.fileContents.invalidate(paths, 'index');
  }

  private contentChanged(): void {
    this.invalidate('status');
  }

  private historyChanged(success: boolean): void {
    this.invalidate('status');
    this.invalidate('head');
    this.fileContents.invalidate('all', 'history');
    if (success) this.repository.invalidate('refs');
  }

  private syncChanged(): void {
    this.invalidateRepositoryHistory();
    this.fileContents.invalidate('all', 'history');
    this.repository.invalidate('refs');
  }

  private onWorktreeEvents(_events: { path: string }[]): void {
    this.invalidate('status');
  }

  private onWorktreeResync(): void {
    this.invalidate('status');
    this.invalidate('head');
  }

  private computed<T>(name: string, compute: () => Promise<T>): Query<T> {
    return query({
      fetch: async () => this.repository.execute(compute),
      debounceMs: WATCH_DEBOUNCE_MS,
      revalidateEveryMs: REVALIDATE_INTERVAL_MS,
      scope: this.statesScope,
      onError: (error) => this.onError(`${name} ${this.identity.checkoutRoot}`, error),
    });
  }

  private assertActive(): void {
    if (this.disposed) throw new Error('CheckoutResource is disposed');
  }
}
