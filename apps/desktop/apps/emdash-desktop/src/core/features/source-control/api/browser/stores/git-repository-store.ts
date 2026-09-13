import {
  localBranchRefSchema,
  remoteBranchRefSchema,
  toBranchRef,
  type FetchPrForReviewOptions,
  type GitBranchRef,
  type GitRefsState,
  type GitRemote,
  type GitRemotesState,
  type LocalBranch,
  type RemoteBranch,
} from '@emdash/core/runtimes/git/api';
import { err } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { observe, pin, remote, type RemoteModel } from '@emdash/wire/state';
import { computed, makeObservable, observable, reaction, runInAction } from 'mobx';
import { buildRendererRepoFacts } from '@core/features/projects/api/browser/effective-settings/renderer-repo-facts';
import type { ProjectHostAccess } from '@core/features/projects/api/browser/stores/project-context';
import type { ProjectSettingsStore } from '@core/features/projects/api/browser/stores/project-settings-store';
import type {
  HostObservation,
  ProjectHostObservation,
} from '@core/features/projects/api/host-observation';
import type { ProviderRepositoryResult } from '@core/features/repository/api';
import { getRepositoryClient } from '@core/features/repository/api/client';
import {
  getSourceControlClient,
  repositorySelector,
} from '@core/features/source-control/api/browser/client';
import { Resource } from '@core/primitives/async-resource/browser/resource';
import {
  resolveEffectiveGitSettings,
  type EffectiveGitSettings,
  type RepoFacts,
  type StoredProjectGitSettings,
} from '@core/primitives/project-settings/api';
import type { ProviderRepository } from '@core/primitives/repository/api';
import { parseRepositoryRef } from '@core/primitives/repository/api';
import { runDesktopLiveJob } from '@core/primitives/wire/browser/run-live-job';
import { sourceControlContract } from '../..';

type RepositoryModel = typeof sourceControlContract.repository.model;
type RepositoryRemote = RemoteModel<RepositoryModel>;
type RepositoryRemoteMember = ReturnType<RepositoryRemote>;

export class GitRepositoryStore {
  private remote: RepositoryRemote | null = null;
  private model: RepositoryRemoteMember | null = null;
  private remoteScope: Scope | null = null;
  private startPromise: Promise<void> | null = null;
  private started = false;
  private loadError: string | null = null;
  private refsState: GitRefsState | null = null;
  private remotesData: GitRemotesState | null = null;
  private refsObservedAt = 0;
  private remotesObservedAt = 0;

  readonly providerRepositoryInfo: Resource<ProviderRepositoryResult>;
  readonly gitDefaultBranchInfo: Resource<Awaited<ReturnType<typeof loadDefaultBranch>>>;
  private settingsDisposer: (() => void) | null = null;
  private hostDisposer: (() => void) | null = null;

  constructor(
    private readonly projectId: string,
    private readonly settingsStore: ProjectSettingsStore,
    private readonly host: ProjectHostAccess,
    private readonly clock: Clock = systemClock
  ) {
    this.providerRepositoryInfo = new Resource<ProviderRepositoryResult>(
      () => getRepositoryClient().then((client) => client.resolveProvider({ projectId })),
      [{ kind: 'demand' }]
    );
    this.gitDefaultBranchInfo = new Resource(
      () => loadDefaultBranch(this.projectId, this.resolvedBaseRemoteName),
      [{ kind: 'demand' }]
    );
    makeObservable<
      GitRepositoryStore,
      | 'model'
      | 'loadError'
      | 'refsState'
      | 'remotesData'
      | 'storedGitSettings'
      | 'liveModelRepoFacts'
      | 'resolvedBaseRemoteName'
      | 'gitDefaultBranch'
    >(this, {
      model: observable.ref,
      loadError: observable,
      refsState: observable.ref,
      remotesData: observable.ref,
      branches: computed,
      branchRefs: computed,
      refsObservation: computed,
      remotesObservation: computed,
      providerRepositoryObservation: computed,
      localBranches: computed,
      remoteBranches: computed,
      storedGitSettings: computed,
      liveModelRepoFacts: computed,
      resolvedBaseRemoteName: computed,
      repoFacts: computed,
      effectiveGitSettings: computed,
      baseRemote: computed,
      pushRemote: computed,
      defaultBranch: computed,
      defaultBranchRef: computed,
      remotes: computed,
      loading: computed,
      canonicalRepositoryUrl: computed,
      providerRepository: computed,
      pullRequestRepositoryUrl: computed,
      issueRepositoryUrl: computed,
      gitDefaultBranch: computed,
    });
    this.settingsDisposer = reaction(
      () => [
        this.resolvedBaseRemoteName,
        this.storedGitSettings.pushRemote,
        this.storedGitSettings.defaultBranch,
      ],
      () => {
        this.gitDefaultBranchInfo.invalidate();
        this.providerRepositoryInfo.invalidate();
      }
    );
    this.hostDisposer = reaction(
      () => this.host.state.kind,
      (kind, previous) => {
        if (kind !== 'ready' || previous === undefined || previous === 'ready') return;
        void this.retry();
      },
      { fireImmediately: true }
    );
  }

  start(): void {
    if (this.started) return;
    this.started = true;
    this.providerRepositoryInfo.start();
    this.gitDefaultBranchInfo.start();
    void this.ensureStarted();
  }

  async resync(): Promise<void> {
    await this.ensureStarted();
    const model = this.model;
    if (!model) return;
    await Promise.all([model.states.refs.refresh(), model.states.remotes.refresh()]);
  }

  async retry(): Promise<void> {
    const scope = this.remoteScope;
    const remote = this.remote;
    runInAction(() => {
      this.remoteScope = null;
      this.remote = null;
      this.model = null;
      this.startPromise = null;
      this.loadError = null;
    });
    try {
      await remote?.dispose();
    } finally {
      await scope?.dispose();
    }
    this.providerRepositoryInfo.invalidate();
    this.gitDefaultBranchInfo.invalidate();
    if (this.started) await this.ensureStarted();
  }

  refreshLocal(): void {
    void this.resync();
  }

  refreshRemote(): void {
    void this.resync();
    this.providerRepositoryInfo.invalidate();
    this.gitDefaultBranchInfo.invalidate();
  }

  refresh(): void {
    this.refreshRemote();
  }

  dispose(): void {
    this.started = false;
    this.providerRepositoryInfo.dispose();
    this.gitDefaultBranchInfo.dispose();
    this.settingsDisposer?.();
    this.settingsDisposer = null;
    this.hostDisposer?.();
    this.hostDisposer = null;
    const scope = this.remoteScope;
    const remote = this.remote;
    this.remoteScope = null;
    this.remote = null;
    this.model = null;
    this.refsState = null;
    this.remotesData = null;
    void (async () => {
      try {
        await remote?.dispose();
      } finally {
        await scope?.dispose();
      }
    })();
  }

  get loading(): boolean {
    return this.model === null && this.loadError === null;
  }

  get localData() {
    return {
      loading: this.loading,
      data: { localBranches: this.localBranches },
      load: () => this.resync(),
    };
  }

  get remoteData() {
    return {
      loading: this.loading,
      data: {
        remoteBranches: this.remoteBranches,
        remotes: this.remotes,
      },
      load: () => this.resync(),
    };
  }

  get branches(): (LocalBranch | RemoteBranch)[] {
    return this.refs?.branches ?? [];
  }

  get branchRefs(): GitBranchRef[] {
    return this.branches.map(toBranchRef);
  }

  get refsObservation(): ProjectHostObservation<GitRefsState> {
    return this.host.observe(
      this.refsState
        ? { kind: 'observed', value: this.refsState, observedAt: this.refsObservedAt }
        : { kind: 'never-observed' }
    );
  }

  get remotesObservation(): ProjectHostObservation<GitRemotesState> {
    return this.host.observe(
      this.remotesData
        ? { kind: 'observed', value: this.remotesData, observedAt: this.remotesObservedAt }
        : { kind: 'never-observed' }
    );
  }

  get providerRepositoryObservation(): ProjectHostObservation<ProviderRepositoryResult> {
    return this.host.observe(
      this.providerRepositoryInfo.data
        ? {
            kind: 'observed',
            value: this.providerRepositoryInfo.data,
            observedAt: this.providerRepositoryInfo.lastUpdatedAt,
          }
        : { kind: 'never-observed' }
    );
  }

  observeHost<T>(observation: HostObservation<T>): ProjectHostObservation<T> {
    return this.host.observe(observation);
  }

  get localBranches(): LocalBranch[] {
    return this.branches.filter((branch): branch is LocalBranch => branch.type === 'local');
  }

  get remoteBranches(): RemoteBranch[] {
    return this.branches.filter((branch): branch is RemoteBranch => branch.type === 'remote');
  }

  /**
   * The effective git settings with provenance, resolved by the blessed
   * resolver over this store's own live-model facts (spec: github-git-settings
   * §2). Surfaces that display an effective value read provenance from here.
   */
  get effectiveGitSettings(): EffectiveGitSettings {
    return resolveEffectiveGitSettings(this.storedGitSettings, this.repoFacts);
  }

  /**
   * The blessed resolver's repo facts from the synced live model: remotes with
   * host, remote branches, local branches, and remote HEADs from the refs
   * state, with the async default-branch lookup (network `remote show`
   * fallback) filling in the effective base remote's HEAD when refs don't
   * know it.
   */
  get repoFacts(): RepoFacts {
    const facts = this.liveModelRepoFacts;
    const baseRemoteName = this.resolvedBaseRemoteName;
    const fetchedHead = this.gitDefaultBranch;
    if (baseRemoteName === null || !fetchedHead) return facts;
    return {
      ...facts,
      remotes: facts.remotes.map((remote) =>
        remote.name === baseRemoteName && remote.headBranch === null
          ? { ...remote, headBranch: fetchedHead }
          : remote
      ),
    };
  }

  /** The effective base remote; null when the repository has no remotes. */
  get baseRemote(): GitRemote | null {
    return this.remoteByName(this.effectiveGitSettings.baseRemote.value);
  }

  /** The effective push remote; null when the repository has no remotes. */
  get pushRemote(): GitRemote | null {
    return this.remoteByName(this.effectiveGitSettings.pushRemote.value);
  }

  get remotes(): GitRemote[] {
    return this.remotesState?.remotes ?? [];
  }

  get canonicalRepositoryUrl(): string | null {
    const baseRemote = this.baseRemote;
    if (baseRemote === null) return null;
    return parseRepositoryRef(baseRemote.url)?.repositoryUrl ?? null;
  }

  get providerRepository(): ProviderRepository | null {
    const result = this.providerRepositoryInfo.data;
    return result?.success ? result.data : null;
  }

  get pullRequestRepositoryUrl(): string | null {
    const repository = this.providerRepository;
    return repository?.capabilities.pullRequests ? repository.repositoryUrl : null;
  }

  get issueRepositoryUrl(): string | null {
    const repository = this.providerRepository;
    return repository?.capabilities.issues ? repository.repositoryUrl : null;
  }

  /**
   * The effective default branch mapped onto the live model's branch objects.
   * Undefined when the resolver answers unresolvable, or when the resolved
   * branch (e.g. a remote HEAD known only via `remote show`) has no local ref
   * yet.
   */
  get defaultBranch(): LocalBranch | RemoteBranch | undefined {
    const resolved = this.effectiveGitSettings.defaultBranch.value;
    if (resolved === null) return undefined;
    if (resolved.remote === null) {
      const ref = localBranchRefSchema.parse(`refs/heads/${resolved.branch}`);
      return this.localBranches.find((branch) => branch.ref === ref);
    }
    const ref = remoteBranchRefSchema.parse(`refs/remotes/${resolved.remote}/${resolved.branch}`);
    return this.remoteBranches.find(
      (branch) => branch.ref === ref && branch.remote.name === resolved.remote
    );
  }

  get defaultBranchRef(): GitBranchRef | undefined {
    const branch = this.defaultBranch;
    return branch ? toBranchRef(branch) : undefined;
  }

  async fetchRemote() {
    const baseRemote = this.baseRemote;
    if (baseRemote === null) {
      return err({ type: 'no_remote' as const, message: 'This repository has no git remotes.' });
    }
    const client = await getSourceControlClient();
    return runDesktopLiveJob(sourceControlContract.repository.fetch, client.repository.fetch, {
      ...repositorySelector(this.projectId),
      remote: baseRemote.name,
    });
  }

  async addRemote(name: string, url: string) {
    const model = await this.requireModel();
    const invocation = await model.mutations.addRemote({ name, url });
    if (invocation.result.success) await invocation.settled;
    return invocation.result;
  }

  async fetchPrForReview(options: FetchPrForReviewOptions) {
    const client = await getSourceControlClient();
    return runDesktopLiveJob(
      sourceControlContract.repository.fetchPrForReview,
      client.repository.fetchPrForReview,
      { ...repositorySelector(this.projectId), options }
    );
  }

  /** Maps a resolved remote name back onto the live model's remote object. */
  private remoteByName(name: string | null): GitRemote | null {
    if (name === null) return null;
    return this.remotes.find((remote) => remote.name === name) ?? null;
  }

  private get refs(): GitRefsState | null {
    return this.refsState;
  }

  private get remotesState(): GitRemotesState | null {
    return this.remotesData;
  }

  /** Stored explicit git choices (absence = infer) — the resolver input. */
  private get storedGitSettings(): StoredProjectGitSettings {
    return this.settingsStore.domains?.gitIdentity.stored ?? {};
  }

  /** Repo facts from the synced live model alone (remote HEADs from refs). */
  private get liveModelRepoFacts(): RepoFacts {
    return buildRendererRepoFacts({
      remotes: this.remotes,
      branches: this.branches,
      remoteHeads: this.refs?.remoteHeads ?? [],
    });
  }

  /**
   * The effective base remote name resolved over refs-only facts. The async
   * remote-HEAD lookup is keyed off this name; base-remote resolution never
   * reads remote HEADs, so the lookup cannot feed back into it.
   */
  private get resolvedBaseRemoteName(): string | null {
    return resolveEffectiveGitSettings(this.storedGitSettings, this.liveModelRepoFacts).baseRemote
      .value;
  }

  /**
   * Remote HEAD of the effective base remote from the async lookup; null when
   * the remote genuinely has no known HEAD, undefined while loading or failed.
   */
  private get gitDefaultBranch(): string | null | undefined {
    const result = this.gitDefaultBranchInfo.data;
    return result?.success ? result.data : undefined;
  }

  private ensureStarted(): Promise<void> {
    this.startPromise ??= this.bindRuntime();
    return this.startPromise;
  }

  private async requireModel(): Promise<RepositoryRemoteMember> {
    await this.ensureStarted();
    if (!this.model) throw new Error(this.loadError ?? 'Git repository is unavailable');
    return this.model;
  }

  private async bindRuntime(): Promise<void> {
    const scope = createScope({ label: `git-repository-store:${this.projectId}` });
    try {
      const client = await getSourceControlClient();
      const gitRemote = remote(sourceControlContract.repository.model, client.repository.model, {
        scope,
        lingerMs: 15_000,
      });
      const model = gitRemote(repositorySelector(this.projectId));
      pin(scope, Object.values(model.states));
      await waitForRepositoryModel(model, scope, this.clock, (refs, remotes, refsAt, remotesAt) => {
        this.refsState = refs;
        this.remotesData = remotes;
        this.refsObservedAt = refsAt;
        this.remotesObservedAt = remotesAt;
      });
      if (!this.started) {
        await gitRemote.dispose();
        await scope.dispose();
        return;
      }
      runInAction(() => {
        this.remote = gitRemote;
        this.remoteScope = scope;
        this.model = model;
        this.loadError = null;
      });
    } catch (error) {
      await scope.dispose();
      runInAction(() => {
        this.loadError = error instanceof Error ? error.message : String(error);
      });
    }
  }
}

async function loadDefaultBranch(projectId: string, remote: string | null) {
  // No remotes → no remote HEAD to look up; an honest absent fact.
  if (remote === null) return { success: true as const, data: null };
  const client = await getSourceControlClient();
  const result = await client.repository.getDefaultBranch({
    ...repositorySelector(projectId),
    remote,
  });
  return result.success ? { success: true as const, data: result.data.branch } : result;
}

function waitForRepositoryModel(
  model: RepositoryRemoteMember,
  scope: Scope,
  clock: Clock,
  setData: (
    refs: GitRefsState,
    remotes: GitRemotesState,
    refsObservedAt: number,
    remotesObservedAt: number
  ) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    let resolved = false;
    let refs: GitRefsState | undefined;
    let remotes: GitRemotesState | undefined;
    let refsObservedAt = 0;
    let remotesObservedAt = 0;
    const publish = () => {
      if (!refs || !remotes) return;
      setData(refs, remotes, refsObservedAt, remotesObservedAt);
      if (!resolved) {
        resolved = true;
        resolve();
      }
    };

    observe(
      model.states.refs,
      (current) => {
        runInAction(() => {
          if (current.status === 'error') {
            reject(current.error);
            return;
          }
          if (!current.value) return;
          refs = current.value;
          refsObservedAt = clock.now();
          publish();
        });
      },
      { scope }
    );
    observe(
      model.states.remotes,
      (current) => {
        runInAction(() => {
          if (current.status === 'error') {
            reject(current.error);
            return;
          }
          if (!current.value) return;
          remotes = current.value;
          remotesObservedAt = clock.now();
          publish();
        });
      },
      { scope }
    );
  });
}
