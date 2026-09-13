import { isDeepEqual } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { observe, remote, type RemoteModel } from '@emdash/wire/state';
import { reaction, toJS } from 'mobx';
import type { GitRepositoryStore } from '@core/features/source-control/api/browser/stores/git-repository-store';
import { getTaskPrAssociationStore } from '@core/features/source-control/api/browser/stores/task-source-control-selectors';
import { gitCheckoutStoreToken } from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import type { TaskManagerStore } from '@core/features/tasks/api/browser/stores/task-manager';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import { workspaceRegistry } from '@core/features/workspaces/api/browser/stores/workspace-registry';
import type { Task, WorkspaceObservedPrFacts } from '@core/primitives/tasks/api';
import { pullRequestsContract, selectCurrentPr } from '@core/services/pull-requests/api';
import {
  getPullRequestsRuntimeClient,
  type PullRequestsRuntimeClient,
} from '@core/services/pull-requests/api/client';
import { derivePrAssociation } from './derive-pr-association';
import { derivePrCheckoutDrift } from './derive-pr-checkout-drift';

export class TaskPrSyncCoordinator {
  private readonly scope = createScope({ label: 'task-pr-sync-coordinator' });
  private syncScope: Scope | null = null;
  private syncRemotePromise: Promise<RemoteModel<typeof pullRequestsContract.syncState>> | null =
    null;
  private generation = 0;
  /** The PR cache's last-sync stamp for the watched repository ("as of last sync"). */
  private lastSyncedAt: number | null = null;
  private readonly disposeGitHeadReaction: () => void;
  private readonly disposeRepositoryReaction: () => void;

  constructor(
    private readonly tasks: TaskManagerStore,
    private readonly repository: GitRepositoryStore
  ) {
    // Association and drift inputs: the checkout store's live head plus the mirror's
    // observed facts (breadcrumb, upstream, branch, head OID, ahead/behind counts) —
    // observation changes must re-derive even when the local checkout never moved
    // (e.g. the host scan delivers a breadcrumb or sees the follow move the head).
    this.disposeGitHeadReaction = reaction(
      () =>
        [...tasks.tasks.values()].filter(isRegistered).map((store) => {
          const git = getTaskGitCheckoutStore(store);
          const observed = store.workspaceObservedPr;
          return [
            store.workspaceId,
            (store.data as Task).workspaceId ?? '',
            store.workspaceObservedStatus ?? '',
            git?.branchName ?? '',
            git?.headOid ?? '',
            observed?.branch ?? '',
            observed?.prBreadcrumb ?? '',
            observed?.upstream?.mergeRef ?? '',
            observed?.upstream?.remoteUrl ?? '',
            observed?.headOid ?? '',
            observed?.ahead ?? '',
            observed?.behind ?? '',
          ].join(':');
        }),
      () => this.reloadAll()
    );
    this.disposeRepositoryReaction = reaction(
      () => repository.pullRequestRepositoryUrl,
      (repositoryUrl) => {
        void this.watchSync(repositoryUrl);
        this.reloadAll();
      },
      { fireImmediately: true }
    );
  }

  dispose(): void {
    this.generation++;
    void this.syncScope?.dispose();
    this.syncScope = null;
    void this.scope.dispose();
    this.disposeGitHeadReaction();
    this.disposeRepositoryReaction();
  }

  private reloadAll(): void {
    for (const store of this.tasks.tasks.values()) {
      if (isRegistered(store)) void this.reloadTask(store);
    }
  }

  /**
   * Re-derives the task's PR association from observed facts, validated against the
   * PR cache on this read (pr-workspace-model spec, Association): breadcrumb, then
   * gh-convention recognition, then head-branch matching. Cache lookup failures keep
   * the current association; the next observation or sync re-derives.
   *
   * The checkout-drift state (spec, Staleness) is derived on the same read: the
   * observed head OID joined with the associated PR's cached head OID, stamped with
   * the cache's last-sync time.
   */
  private async reloadTask(store: TaskStore): Promise<void> {
    if (!isRegistered(store)) return;
    const repositoryUrl = this.repository.pullRequestRepositoryUrl;
    // Missing repository context prevents a refresh; it does not prove that the
    // task's last-known PR stopped existing.
    if (!repositoryUrl) return;
    const association = getTaskPrAssociationStore(store);
    const inputs = associationInputs(store);
    // With no checkout evidence, there is nothing authoritative that can supersede
    // the task's last-known association.
    if (inputs.observed === null && inputs.checkoutBranch === null) return;

    let prs: Task['prs'];
    try {
      const client = await getPullRequestsRuntimeClient();
      prs = await derivePrAssociation({
        observed: inputs.observed,
        checkoutBranch: inputs.checkoutBranch,
        lookups: cacheLookups(client, repositoryUrl),
      });
    } catch {
      return;
    }
    // Drop stale results: another reload owns the write when the inputs moved.
    if (this.repository.pullRequestRepositoryUrl !== repositoryUrl) return;
    if (!isDeepEqual(associationInputs(store), inputs)) return;
    // Drift is derived against the PR the panel renders (selectCurrentPr).
    const drift = derivePrCheckoutDrift({
      observed: inputs.observed,
      pr: selectCurrentPr(prs) ?? null,
      syncedAt: this.lastSyncedAt,
    });
    if (!isRegistered(store)) return;
    association.setAssociation(prs, drift);
  }

  private async watchSync(repositoryUrl: string | null): Promise<void> {
    const generation = ++this.generation;
    void this.syncScope?.dispose();
    this.syncScope = null;
    this.lastSyncedAt = null;
    if (!repositoryUrl) return;

    const syncRemote = await this.getSyncRemote();
    if (generation !== this.generation) return;
    const syncScope = this.scope.child(`sync:${repositoryUrl}`);
    this.syncScope = syncScope;
    let previousLastSyncedAt: number | undefined;
    const member = syncRemote({ repositoryUrl });
    observe(
      member.states.state,
      (state) => {
        const value = state.value;
        if (value?.lastSyncedAt !== undefined) this.lastSyncedAt = value.lastSyncedAt;
        if (
          value?.phase !== 'idle' ||
          value.lastSyncedAt === undefined ||
          value.lastSyncedAt === previousLastSyncedAt
        ) {
          return;
        }
        previousLastSyncedAt = value.lastSyncedAt;
        this.reloadAll();
      },
      { scope: syncScope }
    );
  }

  private getSyncRemote(): Promise<RemoteModel<typeof pullRequestsContract.syncState>> {
    this.syncRemotePromise ??= getPullRequestsRuntimeClient().then((client) =>
      remote(pullRequestsContract.syncState, client.syncState, {
        scope: this.scope,
        lingerMs: 15_000,
      })
    );
    return this.syncRemotePromise;
  }
}

function getTaskGitCheckoutStore(store: TaskStore) {
  return store.workspaceId
    ? workspaceRegistry.get(store.workspaceId)?.get(gitCheckoutStoreToken)
    : undefined;
}

function isRegistered(store: TaskStore): boolean {
  return store.state !== 'unregistered';
}

type AssociationInputs = {
  observed: WorkspaceObservedPrFacts | null;
  checkoutBranch: string | null;
};

function associationInputs(store: TaskStore): AssociationInputs {
  return {
    observed: toJS(store.workspaceObservedPr),
    checkoutBranch: getTaskGitCheckoutStore(store)?.branchName ?? null,
  };
}

/** Cache reads for the derivation; failed lookups reject so the reload aborts. */
function cacheLookups(client: PullRequestsRuntimeClient, repositoryUrl: string) {
  return {
    async byUrl(url: string) {
      const result = await client.getPullRequestByUrl({ repositoryUrl, url });
      if (!result.success) throw new Error(`PR cache lookup failed: ${result.error.type}`);
      return result.data.pr;
    },
    async byBranch(branch: string) {
      const result = await client.getPullRequestsForBranch({ repositoryUrl, branch });
      if (!result.success) throw new Error(`PR cache lookup failed: ${result.error.type}`);
      return result.data.prs;
    },
  };
}
