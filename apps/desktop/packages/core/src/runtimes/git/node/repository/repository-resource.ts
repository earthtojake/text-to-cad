import type { Unsubscribe } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import type { KeyedMutex } from '@emdash/shared/concurrency';
import { query, type ExposedMutationContext, type Query } from '@emdash/wire/state';
import {
  type gitRepositoryContract,
  type GitRefsState,
  type GitRemotesState,
  type GitWorktreesState,
} from '#runtimes/git/api';
import type { CheckoutId, RepositoryIdentity } from '#runtimes/git/node/allocation/identity';
import type { CheckoutResource } from '#runtimes/git/node/checkout/checkout-resource';
import type { GitOperationContext } from '#runtimes/git/node/exec/operation-context';
import { requireWatchReady, type IWatchService, type WatchHandle } from '#services/fs-watch/api';
import type { GitRepository } from './git-repository';
import { RepositoryFamilyLane } from './repository-family-lane';
import { classifyGitWatchEvents, type WorktreeWatchEffects } from './watch-classifier';

const WATCH_DEBOUNCE_MS = 100;
const REVALIDATE_INTERVAL_MS = 5 * 60_000;

type RepositoryModel = typeof gitRepositoryContract.model;
type RepositoryStateName = Extract<keyof RepositoryModel['states'], string>;
type RepositoryMutationName = Extract<keyof RepositoryModel['mutations'], string>;
type RepositoryMutationContext<Name extends RepositoryMutationName> = ExposedMutationContext<
  RepositoryModel,
  Name
>;

export type RepositoryResourceOptions = Readonly<{
  identity: RepositoryIdentity;
  commands: GitRepository;
  watcher: IWatchService;
  objectStoreMutex: KeyedMutex;
  onError?: (context: string, error: unknown) => void;
}>;

/** One canonical repository, including commands, live state, ordering, and reconciliation. */
export class RepositoryResource {
  readonly identity: RepositoryIdentity;

  private readonly commands: GitRepository;
  private readonly lane = new RepositoryFamilyLane();
  private readonly statesScope = createScope({ label: 'git-repository-states' });
  private readonly states: {
    refs: Query<GitRefsState>;
    remotes: Query<GitRemotesState>;
  };
  private readonly checkouts = new Map<CheckoutId, CheckoutResource>();
  private readonly commonDirWatch: WatchHandle;
  private readonly onError: (context: string, error: unknown) => void;
  private disposed = false;

  static async create(options: RepositoryResourceOptions): Promise<RepositoryResource> {
    const resource = new RepositoryResource(options);
    try {
      await requireWatchReady(resource.commonDirWatch);
      return resource;
    } catch (error) {
      await resource.dispose();
      throw error;
    }
  }

  private constructor(private readonly options: RepositoryResourceOptions) {
    this.identity = options.identity;
    this.commands = options.commands;
    this.onError = options.onError ?? (() => {});
    this.states = {
      refs: this.computed('refs', () => this.commands.getRefs()),
      remotes: this.computed('remotes', () => this.commands.getRemotes()),
    };
    this.commonDirWatch = options.watcher.watch(
      this.identity.gitCommonDir,
      (events) => this.onCommonDirEvents(events),
      {
        ignore: ['objects/**'],
        onResync: () => this.onCommonDirResync(),
      }
    );
  }

  state(name: 'refs'): Query<GitRefsState>;
  state(name: 'remotes'): Query<GitRemotesState>;
  state(name: RepositoryStateName) {
    return this.states[name];
  }

  invalidate(name: RepositoryStateName): void {
    this.states[name].invalidate();
  }

  listWorktrees(): Promise<GitWorktreesState> {
    this.assertActive();
    return this.commands.listWorktrees();
  }

  getDefaultBranch(remote: string): Promise<string | null> {
    this.assertActive();
    return this.commands.getDefaultBranch(remote);
  }

  async addRemote(context: RepositoryMutationContext<'addRemote'>) {
    const result = await this.execute(() =>
      this.commands.addRemote(context.input.name, context.input.url)
    );
    if (result.success) {
      this.invalidate('remotes');
      this.invalidate('refs');
    }
    return result;
  }

  async fetch(
    remote: string | undefined,
    context: GitOperationContext,
    options: { refspec?: string; force?: boolean } = {}
  ) {
    const result = await this.execute(() => this.commands.fetch(remote, context, options), true);
    this.invalidate('refs');
    if (result.success) this.invalidateCheckoutHistory();
    else this.invalidate('remotes');
    return result;
  }

  async fetchPrForReview(
    options: Parameters<GitRepository['fetchPrForReview']>[0],
    context: GitOperationContext
  ) {
    const result = await this.execute(() => this.commands.fetchPrForReview(options, context), true);
    this.invalidate('refs');
    this.invalidate('remotes');
    if (result.success) this.invalidateCheckoutHistory();
    return result;
  }

  registerCheckout(checkout: CheckoutResource): Unsubscribe {
    this.assertActive();
    const id = checkout.identity.checkoutId;
    this.checkouts.set(id, checkout);
    return () => {
      if (this.checkouts.get(id) === checkout) this.checkouts.delete(id);
    };
  }

  execute<T>(run: () => Promise<T>, objectTransfer = false): Promise<T> {
    this.assertActive();
    return this.lane.run(() =>
      objectTransfer
        ? this.options.objectStoreMutex.runExclusive(this.identity.objectStoreId, run)
        : run()
    );
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    await this.commonDirWatch.release();
    await this.lane.drain();
    await this.statesScope.dispose();
    this.checkouts.clear();
  }

  private refsChanged(): void {
    this.invalidate('refs');
    this.invalidateCheckoutHistory();
  }

  private invalidateCheckoutHistory(): void {
    for (const checkout of this.checkouts.values()) checkout.invalidateRepositoryHistory();
  }

  private onCommonDirEvents(events: Parameters<typeof classifyGitWatchEvents>[0]): void {
    const classification = classifyGitWatchEvents(events, this.layout());
    if (classification.repo.refs) this.refsChanged();
    if (classification.repo.remotes) this.invalidate('remotes');
    for (const [id, effects] of classification.worktrees) {
      this.applyWorktreeWatchEffects(id as CheckoutId, effects);
    }
  }

  private onCommonDirResync(): void {
    for (const state of Object.values(this.states)) state.invalidate();
    for (const checkout of this.checkouts.values()) {
      checkout.applyRepositoryWatchEffects({ status: true, head: true });
    }
  }

  private applyWorktreeWatchEffects(id: CheckoutId, effects: WorktreeWatchEffects): void {
    this.checkouts.get(id)?.applyRepositoryWatchEffects(effects);
  }

  private layout() {
    return {
      gitCommonDir: this.identity.gitCommonDir,
      worktrees: [...this.checkouts.values()].map((checkout) => ({
        id: checkout.identity.checkoutId,
        gitDir: checkout.identity.gitDir,
        worktree: checkout.identity.checkoutRoot,
      })),
    };
  }

  private computed<T>(name: string, compute: () => Promise<T>): Query<T> {
    return query({
      fetch: async () => this.lane.run(compute),
      debounceMs: WATCH_DEBOUNCE_MS,
      revalidateEveryMs: REVALIDATE_INTERVAL_MS,
      scope: this.statesScope,
      onError: (error) => this.onError(`${name} ${this.identity.gitCommonDir}`, error),
    });
  }

  private assertActive(): void {
    if (this.disposed) throw new Error('RepositoryResource is disposed');
  }
}
