import { encodeResourceUri } from '@emdash/core/primitives/path/api';
import {
  shortName,
  type CheckoutHeadState,
  type CheckoutStatusState,
  type GitChange,
} from '@emdash/core/runtimes/git/api';
import { err, ok } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { runWithTimeout, TimeoutError } from '@emdash/shared/scheduling';
import {
  cell,
  derived,
  observe,
  optimistic,
  pin,
  remote,
  snapshot,
  type Cell,
  type OptimisticView,
  type RemoteModel,
} from '@emdash/wire/state';
import { computed, makeObservable, observable, runInAction } from 'mobx';
import { getFilesClient } from '@core/features/files/api/browser/client';
import {
  checkoutSelector,
  getSourceControlClient,
  gitFilePath,
} from '@core/features/source-control/api/browser/client';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import { resolveWorkspacePath } from '@core/features/workspaces/api/browser/workspace-path';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { runDesktopLiveJob } from '@core/primitives/wire/browser/run-live-job';
import { sourceControlContract } from '../../api';
import {
  type CheckoutChangesState,
  emptyCheckoutChangesState,
  projectCheckoutChanges,
  reduceStageAll,
  reduceStageFiles,
  reduceUnstageAll,
  reduceUnstageFiles,
} from './checkout-changes-state';

const TOO_MANY_FILES_MSG = 'Too many files changed to display';
// A healthy checkout model emits status and head within a few seconds; a wait
// this long means the Git runtime is wedged, so surface an error the panel can
// show (with retry) instead of leaving the store in a permanent loading state.
const CHECKOUT_MODEL_STARTUP_TIMEOUT_MS = 30_000;
const MAX_UNTRACKED_STAT_BYTES = 2 * 1024 * 1024;
type CheckoutModel = typeof sourceControlContract.checkout.model;
type CheckoutRemote = RemoteModel<CheckoutModel>;
type CheckoutRemoteMember = ReturnType<CheckoutRemote>;

export class GitCheckoutStore {
  private remote: CheckoutRemote | null = null;
  private model: CheckoutRemoteMember | null = null;
  private remoteScope: Scope | null = null;
  private startPromise: Promise<void> | null = null;
  private started = false;
  private syncError: string | null = null;
  private statusData: CheckoutStatusState | null = null;
  private headData: CheckoutHeadState | null = null;
  private changesMetadata: Cell<CheckoutChangesState> | null = null;
  private changesView: OptimisticView<CheckoutChangesState> | null = null;
  private changesRequest = 0;
  private stagedChanges: GitChange[] = [];
  private unstagedChanges: GitChange[] = [];
  private revision = 0;

  constructor(
    private readonly projectId: string,
    private readonly workspaceId: string,
    readonly workspacePath: string,
    private readonly sshConnectionId?: string
  ) {
    makeObservable<
      GitCheckoutStore,
      | 'model'
      | 'syncError'
      | 'statusData'
      | 'headData'
      | 'stagedChanges'
      | 'unstagedChanges'
      | 'revision'
    >(this, {
      model: observable.ref,
      syncError: observable,
      statusData: observable.ref,
      headData: observable.ref,
      stagedChanges: observable.ref,
      unstagedChanges: observable.ref,
      revision: observable,
      fileChanges: computed,
      stagedFileChanges: computed,
      unstagedFileChanges: computed,
      totalLinesAdded: computed,
      totalLinesDeleted: computed,
      hasData: computed,
      isLoading: computed,
      error: computed,
      isPublished: computed,
      aheadCount: computed,
      behindCount: computed,
      branchName: computed,
      headOid: computed,
      headKind: computed,
      headDisplay: computed,
      statusRevision: computed,
    });
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    void this.ensureStarted();
  }

  async resync(): Promise<void> {
    await this.ensureStarted();
    const model = this.model;
    if (!model) return;
    await Promise.all([model.states.status.refresh(), model.states.head.refresh()]);
    await this.refreshDiffMetadata();
  }

  async retry(): Promise<void> {
    this.changesRequest += 1;
    const scope = this.remoteScope;
    const remote = this.remote;
    runInAction(() => {
      this.remoteScope = null;
      this.remote = null;
      this.model = null;
      this.startPromise = null;
      this.syncError = null;
      this.statusData = null;
      this.headData = null;
      this.changesMetadata = null;
      this.changesView = null;
      this.stagedChanges = [];
      this.unstagedChanges = [];
    });
    try {
      await remote?.dispose();
    } finally {
      await scope?.dispose();
    }
    if (this.started) await this.ensureStarted();
  }

  dispose(): void {
    this.started = false;
    this.changesRequest += 1;
    const scope = this.remoteScope;
    const remote = this.remote;
    this.remoteScope = null;
    this.remote = null;
    this.model = null;
    this.statusData = null;
    this.headData = null;
    this.changesMetadata = null;
    this.changesView = null;
    void (async () => {
      try {
        await remote?.dispose();
      } finally {
        await scope?.dispose();
      }
    })();
  }

  get statusRevision(): number {
    return this.revision;
  }

  get fileChanges(): GitChange[] {
    const combined = new Map<string, GitChange>();
    for (const change of [...this.stagedChanges, ...this.unstagedChanges]) {
      const current = combined.get(change.path);
      combined.set(
        change.path,
        current
          ? {
              path: change.path,
              status: current.status === change.status ? change.status : 'modified',
              additions: current.additions + change.additions,
              deletions: current.deletions + change.deletions,
            }
          : change
      );
    }
    return [...combined.values()];
  }

  get stagedFileChanges(): GitChange[] {
    return this.stagedChanges;
  }

  get unstagedFileChanges(): GitChange[] {
    return this.unstagedChanges;
  }

  get totalLinesAdded(): number {
    return this.fileChanges.reduce((sum, change) => sum + change.additions, 0);
  }

  get totalLinesDeleted(): number {
    return this.fileChanges.reduce((sum, change) => sum + change.deletions, 0);
  }

  get hasData(): boolean {
    return this.model !== null;
  }

  get isLoading(): boolean {
    return !this.hasData && this.syncError === null;
  }

  get error(): string | undefined {
    const status = this.status;
    if (status?.kind === 'too-many-files') return TOO_MANY_FILES_MSG;
    if (status?.kind === 'error') return status.message;
    return this.syncError ?? undefined;
  }

  get branchName(): string | null {
    const head = this.head;
    return !head || head.kind === 'detached' ? null : shortName(head.ref);
  }

  get headOid(): string | null {
    const head = this.head;
    return head?.kind === 'branch' || head?.kind === 'detached' ? head.oid : null;
  }

  get headKind(): CheckoutHeadState['kind'] {
    return this.head?.kind ?? 'branch';
  }

  get headDisplay(): string | null {
    const head = this.head;
    if (!head) return null;
    return head.kind === 'detached' ? head.shortHash : shortName(head.ref);
  }

  get isPublished(): boolean {
    const head = this.head;
    if (!head || head.kind === 'detached') return false;
    return head.upstream.kind === 'remote';
  }

  get aheadCount(): number {
    const head = this.head;
    return head &&
      head.kind !== 'detached' &&
      head.upstream.kind !== 'none' &&
      head.upstream.tracking.kind === 'resolved'
      ? head.upstream.tracking.ahead
      : 0;
  }

  get behindCount(): number {
    const head = this.head;
    return head &&
      head.kind !== 'detached' &&
      head.upstream.kind !== 'none' &&
      head.upstream.tracking.kind === 'resolved'
      ? head.upstream.tracking.behind
      : 0;
  }

  async stageFiles(paths: string[]) {
    const { model, view } = await this.requireChangesMutation();
    return view.run(model.mutations.stage, { paths: paths.map(gitFilePath) }, reduceStageFiles);
  }

  async stageAllFiles() {
    const { model, view } = await this.requireChangesMutation();
    return view.run(model.mutations.stageAll, {}, reduceStageAll);
  }

  async unstageFiles(paths: string[]) {
    const { model, view } = await this.requireChangesMutation();
    return view.run(model.mutations.unstage, { paths: paths.map(gitFilePath) }, reduceUnstageFiles);
  }

  async unstageAllFiles() {
    const { model, view } = await this.requireChangesMutation();
    return view.run(model.mutations.unstageAll, {}, reduceUnstageAll);
  }

  async discardFiles(paths: string[]) {
    const model = await this.requireModel();
    return settleMutation(model.mutations.revert({ paths: paths.map(gitFilePath) }));
  }

  async discardAllFiles() {
    const model = await this.requireModel();
    return settleMutation(model.mutations.revertAll({}));
  }

  async commit(message: string) {
    const model = await this.requireModel();
    const result = await settleMutation(model.mutations.commit({ message }));
    return result.success ? ok() : err(result.error);
  }

  async push() {
    const client = await getSourceControlClient();
    // Null push remote (no remotes) degrades to a push without an explicit
    // remote — the same behavior as when the repository store is missing.
    const remote = getGitRepositoryStore(this.projectId)?.pushRemote?.name;
    return runDesktopLiveJob(sourceControlContract.checkout.push, client.checkout.push, {
      ...checkoutSelector(this.workspaceId),
      options: remote ? { remote } : undefined,
    });
  }

  async publishCurrentBranch() {
    const pushRemote = getGitRepositoryStore(this.projectId)?.pushRemote;
    if (pushRemote === null || pushRemote === undefined) {
      return err({ type: 'no_remote' as const, message: 'This repository has no git remotes.' });
    }
    const model = await this.requireModel();
    const client = await getSourceControlClient();
    const result = await runDesktopLiveJob(
      sourceControlContract.checkout.publish,
      client.checkout.publish,
      {
        ...checkoutSelector(this.workspaceId),
        remote: pushRemote.name,
      }
    );
    if (result.success) await model.states.head.refresh();
    return result;
  }

  async pull() {
    const client = await getSourceControlClient();
    return runDesktopLiveJob(
      sourceControlContract.checkout.pull,
      client.checkout.pull,
      checkoutSelector(this.workspaceId)
    );
  }

  private get status(): CheckoutStatusState | null {
    return this.statusData;
  }

  private get head(): CheckoutHeadState | null {
    return this.headData;
  }

  private ensureStarted(): Promise<void> {
    this.startPromise ??= this.bindRuntime();
    return this.startPromise;
  }

  private async requireModel(): Promise<CheckoutRemoteMember> {
    await this.ensureStarted();
    if (!this.model) throw new Error(this.syncError ?? 'Git checkout is unavailable');
    return this.model;
  }

  private async requireChangesMutation(): Promise<{
    model: CheckoutRemoteMember;
    view: OptimisticView<CheckoutChangesState>;
  }> {
    const model = await this.requireModel();
    const view = this.changesView;
    if (!view) throw new Error(this.syncError ?? 'Git checkout changes are unavailable');
    return { model, view };
  }

  private async bindRuntime(): Promise<void> {
    const scope = createScope({ label: `git-checkout-store:${this.workspaceId}` });
    let checkoutRemote: CheckoutRemote | null = null;
    try {
      const client = await getSourceControlClient();
      checkoutRemote = remote(sourceControlContract.checkout.model, client.checkout.model, {
        scope,
        lingerMs: 15_000,
      });
      const model = checkoutRemote(checkoutSelector(this.workspaceId));
      const changesMetadata = cell(emptyCheckoutChangesState());
      const baseChanges = derived(() =>
        projectCheckoutChanges(snapshot(model.states.status).value, snapshot(changesMetadata).value)
      );
      const changesView = optimistic(baseChanges);
      observe(
        changesView,
        (current) => {
          runInAction(() => {
            this.stagedChanges = current.value?.staged ?? [];
            this.unstagedChanges = current.value?.unstaged ?? [];
          });
        },
        { scope }
      );
      pin(scope, Object.values(model.states));
      await runWithTimeout(
        () =>
          waitForCheckoutModel(model, scope, {
            setStatus: (status) => {
              this.statusData = status;
              this.revision += 1;
              void this.refreshDiffMetadata(changesMetadata);
            },
            setHead: (head) => {
              this.headData = head;
              this.revision += 1;
            },
          }),
        { timeoutMs: CHECKOUT_MODEL_STARTUP_TIMEOUT_MS }
      );
      if (!this.started) {
        await checkoutRemote.dispose();
        await scope.dispose();
        return;
      }
      runInAction(() => {
        this.remote = checkoutRemote;
        this.remoteScope = scope;
        this.model = model;
        this.changesMetadata = changesMetadata;
        this.changesView = changesView;
        this.syncError = null;
      });
    } catch (error) {
      await checkoutRemote?.dispose();
      await scope.dispose();
      runInAction(() => {
        this.syncError =
          error instanceof TimeoutError
            ? 'Timed out waiting for Git status. The Git runtime may be unresponsive.'
            : error instanceof Error
              ? error.message
              : String(error);
      });
    }
  }

  private async refreshDiffMetadata(
    metadata: Cell<CheckoutChangesState> | null = this.changesMetadata
  ): Promise<void> {
    if (!metadata) return;
    const status = this.status;
    if (!status || status.kind !== 'ok') {
      metadata.set(emptyCheckoutChangesState());
      return;
    }
    const request = ++this.changesRequest;
    const client = await getSourceControlClient();
    const selector = checkoutSelector(this.workspaceId);
    const [stagedResult, unstagedResult] = await Promise.all([
      client.checkout.getChangedFiles({ ...selector, target: { kind: 'staged-vs-head' } }),
      client.checkout.getChangedFiles({ ...selector, target: { kind: 'working-vs-index' } }),
    ]);
    if (request !== this.changesRequest || !this.started) return;
    if (!stagedResult.success || !unstagedResult.success) {
      runInAction(() => {
        this.syncError = 'Failed to load changed files';
      });
      return;
    }

    const enriched = projectCheckoutChanges(status, {
      staged: stagedResult.data.files,
      unstaged: unstagedResult.data.files,
    });
    await addUntrackedLineCounts(enriched.unstaged, this.workspacePath, this.sshConnectionId);
    if (request !== this.changesRequest || !this.started) return;
    metadata.set(enriched);
    runInAction(() => {
      this.syncError = null;
    });
  }
}

async function settleMutation<
  Invocation extends Promise<{ result: { success: boolean }; settled: Promise<void> }>,
>(invocationPromise: Invocation): Promise<Awaited<Invocation>['result']> {
  const invocation = await invocationPromise;
  if (invocation.result.success) await invocation.settled;
  return invocation.result;
}

function waitForCheckoutModel(
  model: CheckoutRemoteMember,
  scope: Scope,
  handlers: {
    setStatus(status: CheckoutStatusState): void;
    setHead(head: CheckoutHeadState): void;
  }
): Promise<void> {
  return new Promise((resolve, reject) => {
    let resolved = false;
    let hasStatus = false;
    let hasHead = false;
    const publishReady = () => {
      if (!hasStatus || !hasHead || resolved) return;
      resolved = true;
      resolve();
    };

    observe(
      model.states.status,
      (current) => {
        runInAction(() => {
          if (current.status === 'error') {
            reject(current.error);
            return;
          }
          if (!current.value) return;
          handlers.setStatus(current.value);
          hasStatus = true;
          publishReady();
        });
      },
      { scope }
    );
    observe(
      model.states.head,
      (current) => {
        runInAction(() => {
          if (current.status === 'error') {
            reject(current.error);
            return;
          }
          if (!current.value) return;
          handlers.setHead(current.value);
          hasHead = true;
          publishReady();
        });
      },
      { scope }
    );
  });
}

async function addUntrackedLineCounts(
  changes: GitChange[],
  workspacePath: string,
  sshConnectionId: string | undefined
): Promise<void> {
  const untracked = changes.filter((change) => change.status === 'added' && change.additions === 0);
  if (untracked.length === 0) return;
  const client = await getFilesClient();
  await Promise.all(
    untracked.map(async (change) => {
      const result = await client.fs.readText({
        uri: encodeResourceUri(
          hostFileRefFromNativePath(
            resolveWorkspacePath(workspacePath, change.path),
            sshConnectionId
          )
        ),
        options: { maxBytes: MAX_UNTRACKED_STAT_BYTES },
      });
      if (result.success && !result.data.truncated) {
        change.additions = result.data.content.split('\n').length - 1;
      }
    })
  );
}
