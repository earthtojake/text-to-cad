import crypto from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import { KeyedMutex } from '@emdash/shared/concurrency';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { stableStringify } from '@emdash/shared/util';
import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import {
  cell,
  expose,
  family,
  pokeChannel,
  query,
  type Cell,
  type Family,
  type Query,
} from '@emdash/wire/state';
import type { EnvSource } from '#primitives/exec/api';
import type { StoreHandle } from '#primitives/sqlite-store/api';
// oxlint-disable-next-line emdash/core-module-boundaries -- the registry sequences lifecycle scripts through the scripts runtime (activation-scripts-via-terminals spec); the contract has no services-level home yet
import type { ScriptWorkspaceFacts } from '#runtimes/scripts/api';
import { ConfigModel } from '#services/config-model/node';
import { workspaceRegistryContract } from '../api/contract';
import type {
  ActivateWorkspaceError,
  CreateWorkspaceError,
  CreateWorktreeError,
  DeleteWorkspaceError,
  DeleteWorktreeError,
  MeasureUsageError,
  RunScriptError,
  UpdateWorktreeError,
  WorkspaceNotFoundError,
} from '../api/errors';
import type {
  ActivateWorkspaceInput,
  CreateWorkspaceInput,
  CreateWorktreeInput,
  DeactivateWorkspaceInput,
  DeleteWorkspaceInput,
  DeleteWorktreeInput,
  ImportLegacyLifecycleSettingsInput,
  MeasureUsageInput,
  GetProjectConfigInput,
  PatchPersonalProjectConfigInput,
  ProjectConfigState,
  RefreshWorkspacesInput,
  RetryStepInput,
  RunScriptInput,
  UpdateWorktreeInput,
  WorkspaceGitSetup,
  WorkspaceLifecycleStep,
  WorkspaceLifecycleStepId,
  WorkspaceRecord,
  WorkspaceRecords,
  WorkspaceRemovalAttempt,
  WorkspaceRuntimeOverlay,
  WorkspaceUsage,
} from '../api/schemas';
import { WorkspaceActivationManager, type WorkspaceDeactivationResult } from './activation';
import { BackgroundStepRunner } from './background-steps';
import { readWorkspaceConfig, type WorkspaceConfigEntry } from './config-model';
import { executeCreateWorktree } from './create-worktree';
import { executeDeleteWorktree } from './delete-worktree';
import { createRegistryGitContext, type RegistryGitContext } from './git-context';
import {
  canonicalizeWorkspacePath,
  inspectWorkspacePath,
  type PathInspector,
} from './inspect-path';
import {
  BACKGROUND_STEP_IDS,
  buildCreationLifecycle,
  getLifecycleStep,
  isIncompleteStep,
  SCRIPT_STEP_IDS,
  sortSteps,
  stepIdForStage,
  withLifecycleStep,
  type CreationStageTimeline,
} from './lifecycle';
import { measureWorkspaceUsage } from './measure-usage';
import { WorkspaceRecordStore, type DurableWorkspaceRecord } from './persistence/record-store';
import type { WorkspaceRegistryDb } from './persistence/store';
import {
  applyLegacyLifecycleSettingsImport,
  applyPersonalProjectConfigPatch,
  collectProjectConfigSources,
  resolveProjectConfig,
  type ProjectConfigHostDefaults,
} from './project-config';
import { listRepositoryWorktrees, observeWorkspaceGit } from './scan/observe-git';
import { RegistryScanner, type RegistryScannerDeps, type ScanLanding } from './scan/scanner';
import type { ScanRequest, ScanTarget } from './scan/scheduler';
import {
  createScriptsPlaneRunner,
  DEFAULT_SCRIPT_TIMEOUT_MS,
  failureMessageWithTail,
  ScriptRunsObserver,
  unavailableScriptRunner,
  type ObservedScriptRun,
  type ScriptsClient,
  type WorkspaceScriptRunner,
} from './scripts-plane';
import type { SessionCounter, SessionKiller } from './session-cleanup';
import { executeUpdateWorktree, type UpdateWorktreeExecutionResult } from './update-worktree';

export type WorkspaceRegistryRuntimeOptions = {
  handle: StoreHandle<WorkspaceRegistryDb>;
  env?: EnvSource;
  clock?: Clock;
  logger?: Logger;
  /** Test seam for hosts without git; production always inspects the real filesystem. */
  inspector?: PathInspector;
  /**
   * The git dependency bundle — budget, writer locks, budgeted exec factory. The
   * runtime constructs a real context by default; tests inject one to compose budget
   * behavior with the runtime.
   */
  gitContext?: RegistryGitContext;
  /**
   * Scanner seam for tests: wrap or replace the scan plane (e.g. a recording proxy,
   * a gated observe fake) while the landings stay the runtime's own. Production
   * always builds the real scanner from the same landing and deps.
   */
  createScanner?: (landing: ScanLanding, deps: RegistryScannerDeps) => RegistryScanner;
  /** Invoked after every records change; the component points the scheduler at it. */
  onRecordsChanged?: () => void;
  /** deactivateWorkspace's session-plane step; the component builds it from the session runtimes. */
  killSessions?: SessionKiller;
  /** updateWorktree's "active" guard probe; the component builds it from the same runtimes. */
  countSessions?: SessionCounter;
  /**
   * The scripts runtime client (spec: activation-scripts-via-terminals): activation
   * runs its scripts through it, and the registry observes its run state as the
   * single writer of durable script lifecycle steps. Absent only in tests that
   * exercise sequencing through a fake runner.
   */
  scripts?: ScriptsClient;
  /** Host-level resolver layer. Production reads the host-settings runtime. */
  getHostSettings?: () => Promise<ProjectConfigHostDefaults>;
  activation?: {
    runner?: WorkspaceScriptRunner;
    teardownTimeoutMs?: number;
  };
};

/**
 * The sole writer of the host workspace registry (ADR 0005): clients mutate only through
 * the wire verbs; the scan is the second feeder — it reconciles the registry with the
 * disk (adopt/un-adopt worktrees, flip missing, relink moves) but never converges the
 * disk toward a record. `records` merges durable rows with the in-memory runtime
 * overlay — the overlay dies with the daemon, by design.
 */
export class WorkspaceRegistryRuntime {
  private readonly store: WorkspaceRecordStore;
  private readonly clock: Clock;
  private readonly logger: Logger;
  private readonly inspector: PathInspector;
  private onRecordsChanged: (() => void) | undefined;
  /**
   * Scan self-suppression seam (spec: scan minimization): points at the scheduler's
   * refcounted mute. Background steps hold it while writing into a workspace or a
   * repository's git dir, then request one deliberate scan on settle. A no-op until
   * the component wires the scheduler in.
   */
  private muteScans: (id: string) => () => void = () => () => undefined;
  private readonly overlays = new Map<string, WorkspaceRuntimeOverlay>();
  private readonly recordsCell: Cell<WorkspaceRecords>;
  private readonly projectConfigPokes = pokeChannel<{ workspaceIds?: readonly string[] }>(
    'workspace-registry:project-config'
  );
  private readonly projectMembershipFingerprints = new Map<string, string>();
  private mutationQueue: Promise<unknown> = Promise.resolve();
  /** Exclusive per-workspace claim: activate/deactivate/delete on one record serialize. */
  private readonly workspaceClaims = new KeyedMutex();
  /**
   * The background creation-step chain (copy/push/fetch); runs, retries, and the
   * activation artifact gate all flow through its per-workspace single-flight.
   */
  private readonly backgroundSteps: BackgroundStepRunner;
  /**
   * The `.emdash.json` live model (spec: workspace-lifecycle-v2): one parsed entry per
   * present record, filled at boot / creation / scans — never read from disk inside a
   * creation or activation verb. Worktrees carry their own entry (branches diverge).
   * Cache discipline (coalescing, change detection) lives in the shared ConfigModel.
   */
  private readonly configs = new ConfigModel<WorkspaceConfigEntry>({
    read: (_id, workspacePath) => readWorkspaceConfig(workspacePath),
    onChanged: (id, entry, previous, workspacePath) =>
      this.onConfigChanged(id, entry, previous, workspacePath),
  });
  private readonly bootConfigHydration: Promise<void>;
  private disposed = false;
  private readonly killSessions: SessionKiller;
  private readonly countSessions: SessionCounter;
  private readonly activationManager: WorkspaceActivationManager;
  private readonly scriptsClient: ScriptsClient | null;
  private readonly getHostSettings: () => Promise<ProjectConfigHostDefaults>;
  /** Observation is the single step-writer for script-class lifecycle steps. */
  private readonly scriptRuns: ScriptRunsObserver | null;
  readonly recordsHost: LeasedLiveModelProvider<typeof workspaceRegistryContract.records>;
  private readonly projectConfigs: Family<GetProjectConfigInput, Query<ProjectConfigState>>;
  readonly projectConfigHost: LeasedLiveModelProvider<
    typeof workspaceRegistryContract.projectConfig
  >;
  /** Every registry-spawned git subprocess flows through this context's budget. */
  readonly gitContext: RegistryGitContext;
  /**
   * The scan plane (spec: registry-runtime-carveout): pass bodies, scan lane, idle
   * gate, and untracked caches live on the scanner; results land back through this
   * runtime's re-validated {@link ScanLanding} implementation.
   */
  readonly scanner: RegistryScanner;

  constructor(options: WorkspaceRegistryRuntimeOptions) {
    const env = options.env ?? (async () => process.env);
    this.clock = options.clock ?? systemClock;
    this.logger = options.logger ?? noopLogger;
    this.inspector = options.inspector ?? ((path) => inspectWorkspacePath(path, env));
    this.gitContext = options.gitContext ?? createRegistryGitContext({ env });
    this.onRecordsChanged = options.onRecordsChanged;
    this.store = new WorkspaceRecordStore(options.handle);
    this.killSessions = options.killSessions ?? (async () => undefined);
    this.countSessions = options.countSessions ?? (async () => 0);
    this.scriptsClient = options.scripts ?? null;
    this.getHostSettings = options.getHostSettings ?? (async () => ({}));
    this.scriptRuns = options.scripts
      ? new ScriptRunsObserver({
          client: options.scripts,
          onRun: (run) => this.onScriptRun(run),
        })
      : null;
    this.activationManager = new WorkspaceActivationManager({
      publishActivation: (id, activation) =>
        this.updateOverlay(id, (overlay) => ({ ...overlay, activation })),
      setNotice: (id, script, message) =>
        this.updateOverlay(id, (overlay) => ({
          ...overlay,
          notices: [
            ...overlay.notices.filter((notice) => notice.id !== `script-failed:${script}`),
            {
              id: `script-failed:${script}`,
              kind: 'script-failed',
              script,
              message,
              at: this.clock.now(),
            },
          ],
        })),
      clearNotice: (id, script) =>
        this.updateOverlay(id, (overlay) => ({
          ...overlay,
          notices: overlay.notices.filter((notice) => notice.id !== `script-failed:${script}`),
        })),
      resetScriptSteps: (id, scripts) =>
        void this.enqueue(async () => {
          const record = this.store.get(id);
          if (!record) return;
          // No scripts and no section: nothing to reset — avoid minting an empty one.
          if (!record.lifecycle && scripts.length === 0) return;
          const now = this.clock.now();
          const lifecycle = record.lifecycle ?? { steps: [], preservePatterns: [] };
          // Overwrite, not append: drop past activations' script steps, seed this one's.
          const steps = sortSteps([
            ...lifecycle.steps.filter((step) => !SCRIPT_STEP_IDS.has(step.id)),
            ...scripts.map(
              (script): WorkspaceLifecycleStep => ({
                id: script,
                status: 'pending',
                startedAt: null,
                finishedAt: null,
                params: {},
              })
            ),
          ]);
          const updated: DurableWorkspaceRecord = {
            ...record,
            lifecycle: { ...lifecycle, steps },
            updatedAt: now,
          };
          this.store.update(updated);
          this.publish(updated);
        }).catch((error) => {
          this.logger.warn?.(`resetting script steps for '${id}' failed`, { error });
        }),
      recordScriptStep: (id, script, state) =>
        void this.updateLifecycleStep(id, script, state).catch((error) => {
          this.logger.warn?.(`recording ${script} step for '${id}' failed`, { error });
        }),
      recordActivated: (id, at) =>
        this.enqueue(async () => {
          const record = this.store.get(id);
          if (!record) return;
          const updated: DurableWorkspaceRecord = { ...record, lastActivatedAt: at, updatedAt: at };
          this.store.update(updated);
          this.publish(updated);
        }),
      // The single execution plane: activation scripts run on the scripts runtime
      // (identical env and shellSetup to manual runs, by construction). The fake
      // runner seam remains for sequencing-only tests.
      runner:
        options.activation?.runner ??
        (options.scripts
          ? createScriptsPlaneRunner({
              client: options.scripts,
              factsFor: (workspacePath) => this.scriptFactsFor(workspacePath),
              logger: this.logger,
            })
          : unavailableScriptRunner()),
      teardownTimeoutMs: options.activation?.teardownTimeoutMs,
      // Scripts come from the config live model — no filesystem read inside the
      // activation verb. Boot hydration completes before the model is resolved.
      resolveLifecycleConfig: async (id) => {
        await this.bootConfigHydration;
        const resolved = await this.resolveProjectConfigFor(id);
        return {
          scripts: {
            prepare: resolved?.resolved.prepare?.value,
            setup: resolved?.resolved.setup?.value,
            run: resolved?.resolved.run?.value,
            teardown: resolved?.resolved.teardown?.value,
          },
          shellSetup: resolved?.resolved.shellSetup?.value ?? '',
          autoRunSetup: resolved?.resolved.autoRunSetup.value ?? true,
          autoRunRun: resolved?.resolved.autoRunRun.value ?? false,
        };
      },
      // The artifact gate (dependency gating): prepare/setup wait for the background
      // copy to settle; a terminal copy failure opens the gates anyway.
      awaitArtifacts: (id) => this.backgroundSteps.awaitArtifactCopy(id),
      clock: this.clock,
      logger: this.logger,
    });

    const initial: WorkspaceRecords = {};
    for (const record of this.store.list()) {
      if (record.observedStatus === 'present') {
        this.configs.seed(record.id, { config: {}, parseError: false });
      }
      initial[record.id] = this.toWire(record);
    }
    for (const record of this.store.list()) {
      const projectRoot = this.projectRootFor(record);
      if (projectRoot) {
        this.projectMembershipFingerprints.set(
          projectRoot.id,
          this.projectMembershipFingerprint(projectRoot.id)
        );
      }
    }
    this.recordsCell = cell<WorkspaceRecords>(initial, { name: 'workspace-records' });
    this.recordsHost = expose(workspaceRegistryContract.records, {
      list: () => this.recordsCell,
    });
    this.bootConfigHydration = Promise.resolve().then(() => this.hydrateBootConfigs());
    this.projectConfigs = family(
      (key, scope) =>
        query({
          fetch: async () => {
            await this.bootConfigHydration;
            const state = await this.resolveProjectConfigFor(key.workspaceId);
            if (!state) throw new Error(`Workspace '${key.workspaceId}' was not found`);
            return state;
          },
          pokes: [
            this.projectConfigPokes.subscription(
              (poke) =>
                poke.workspaceIds === undefined || poke.workspaceIds.includes(key.workspaceId)
            ),
          ],
          scope,
        }),
      { key: (key) => key.workspaceId, name: 'project-config' }
    );
    this.projectConfigHost = expose(workspaceRegistryContract.projectConfig, {
      current: (key, scope) => {
        scope.add(this.projectConfigs.retain(key));
        return this.projectConfigs(key);
      },
    });

    // The scan plane: the scanner owns the passes; every landing runs here on the
    // mutation lane, re-validated against the live store (ADR 0001 stays structural).
    const landing: ScanLanding = {
      get: (id) => this.store.get(id) ?? undefined,
      list: () => this.store.list(),
      observation: (id, patch, now) => this.applyObservation(id, patch, now),
      vanished: (id, now) => this.applyVanished(id, now),
      adoption: (record) => this.applyAdoption(record),
      refreshConfig: async (id, workspacePath) => {
        await this.refreshConfig(id, workspacePath);
      },
    };
    const scannerDeps: RegistryScannerDeps = {
      git: this.gitContext,
      clock: this.clock,
      logger: this.logger,
    };
    this.scanner =
      options.createScanner?.(landing, scannerDeps) ?? new RegistryScanner(landing, scannerDeps);

    // The step chain: reads through the store, writes only through the lifecycle
    // step writer, suppresses and settles scans through the runtime's muting seams.
    this.backgroundSteps = new BackgroundStepRunner({
      records: {
        get: (id) => this.store.get(id) ?? undefined,
        list: () => this.store.list(),
      },
      steps: {
        update: (id, stepId, state) => this.updateLifecycleStep(id, stepId, state),
      },
      scans: {
        mute: (id) => this.muteScans(id),
        settle: (request) => this.settleScan(request),
      },
      git: this.gitContext,
      logger: this.logger,
      clock: this.clock,
    });

    // Restart replay: background steps left pending/running (a daemon killed mid-step)
    // re-run exactly once; terminal statuses (failed/succeeded/skipped) are respected.
    // Script steps never replay: runs died with the daemon, so incomplete ones settle
    // as cancelled — the timeline must not show a phantom in-flight run (spec:
    // activation-scripts-via-terminals). The config live model boots alongside: one
    // read per present record, off every blocking path.
    queueMicrotask(() => {
      if (this.disposed) return;
      for (const record of this.store.list()) {
        if (hasIncompleteBackgroundSteps(record)) this.backgroundSteps.ensureRunning(record.id);
        this.settleInterruptedScriptSteps(record);
      }
      this.syncScriptObservers();
    });
  }

  dispose(): void {
    this.disposed = true;
    this.configs.dispose();
    this.scriptRuns?.dispose();
    this.activationManager.dispose();
    this.projectConfigHost.dispose();
    void this.projectConfigs.dispose();
    this.recordsHost.dispose();
  }

  createWorkspace(
    input: CreateWorkspaceInput
  ): Promise<Result<WorkspaceRecord, CreateWorkspaceError>> {
    return this.enqueue(() => this.createWorkspaceLocked(input));
  }

  /**
   * Deactivate-if-active + unregister. Never touches disk; idempotent on absent ids.
   * A failing teardown is a removal-stage failure: recorded durably on the record
   * before the error returns, so the delete stays visible and retryable (ADR 0006).
   */
  deleteWorkspace(input: DeleteWorkspaceInput): Promise<Result<void, DeleteWorkspaceError>> {
    return this.workspaceClaims.runExclusive(input.workspaceId, async () => {
      const record = this.store.get(input.workspaceId);
      if (record) {
        const teardownFailure = await this.deactivateForRemoval(record);
        if (teardownFailure) return err(teardownFailure);
      }
      return await this.enqueue(() => Promise.resolve(this.deleteWorkspaceLocked(input)));
    });
  }

  /**
   * Deactivate + force-remove the worktree artifact (+ branch when asked) + unregister,
   * as one call. Held under the per-workspace claim (serializing against activate/
   * deactivate/delete on this record); the removal itself takes the per-worktree
   * writer lock so probes of that worktree wait (spec: git concurrency model — no
   * repository-level serialization against creations, git's own locking suffices).
   * A removal failure leaves the record registered so the delete stays retryable.
   */
  async deleteWorktree(input: DeleteWorktreeInput): Promise<Result<void, DeleteWorktreeError>> {
    const record = this.store.get(input.workspaceId);
    if (!record) return ok(undefined);
    if (record.kind !== 'worktree') {
      return err({ type: 'not-a-worktree', workspaceId: input.workspaceId });
    }
    const parent = record.parentId === null ? null : this.store.get(record.parentId);
    const repositoryPath = await this.resolveRepositoryPath(record, parent);

    if (repositoryPath === null) {
      return this.workspaceClaims.runExclusive(input.workspaceId, async () => {
        const current = this.store.get(input.workspaceId);
        if (!current) return ok(undefined);
        const teardownFailure = await this.deactivateForRemoval(current);
        if (teardownFailure) return err(teardownFailure);
        if (await isDirectory(current.path)) {
          // Structural: the artifact remains but no repository can prune it — an
          // identical retry cannot converge without user intervention.
          return err(
            await this.recordRemovalFailure(input.workspaceId, {
              stage: 'remove',
              class: 'terminal',
              message: `Cannot resolve the owning repository of '${current.path}'`,
            })
          );
        }
        // Artifact already gone and no repository left to prune: just unregister.
        return await this.enqueue(() =>
          Promise.resolve(this.deleteWorkspaceLocked({ workspaceId: input.workspaceId }))
        );
      });
    }

    return this.workspaceClaims.runExclusive(input.workspaceId, async () => {
      const current = this.store.get(input.workspaceId);
      if (!current) return ok(undefined);
      const teardownFailure = await this.deactivateForRemoval(current);
      if (teardownFailure) return err(teardownFailure);
      const result = await executeDeleteWorktree({
        git: this.gitContext,
        repositoryPath,
        worktreePath: current.path,
        deleteBranch: input.deleteBranch,
        branchHint: current.git?.branch ?? current.creation?.branch ?? null,
      });
      if (result.status === 'failed') {
        return err(
          await this.recordRemovalFailure(input.workspaceId, {
            stage: 'remove',
            class: result.class,
            message: result.message,
          })
        );
      }
      return await this.enqueue(() =>
        Promise.resolve(this.deleteWorkspaceLocked({ workspaceId: input.workspaceId }))
      );
    });
  }

  /**
   * Fast-forwards one worktree's checkout to the desktop-compiled `{remote, sourceRef}`
   * instruction (spec: pr-workspace-model staleness, manual update). The record's own
   * `gitSetup` is deliberately never read — instruction-as-input is what makes
   * pre-model workspaces updatable. Held under the per-workspace claim like the other
   * mutators; the executor takes the per-worktree writer lock around guards + fetch +
   * ff-only so scans never observe a torn checkout. "Active" means live sessions under
   * the worktree path — exactly the set deactivateWorkspace would kill — consulted
   * through the session-count seam. A success writes nothing durable; the trailing
   * deliberate scan feeds the observation (and the desktop's drift state).
   */
  updateWorktree(input: UpdateWorktreeInput): Promise<Result<void, UpdateWorktreeError>> {
    return this.workspaceClaims.runExclusive(input.workspaceId, async () => {
      const record = this.store.get(input.workspaceId);
      if (!record) return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
      if (record.kind !== 'worktree') {
        return err({ type: 'not-a-worktree', workspaceId: input.workspaceId });
      }
      if (record.observedStatus === 'missing') {
        return err({ type: 'workspace-missing', workspaceId: input.workspaceId });
      }
      const parent = record.parentId === null ? null : this.store.get(record.parentId);
      // The update writes into the worktree (the ff checkout) and the shared git dir
      // (the private fetch ref): mute both watchers, then scan once deliberately.
      const releaseWorktree = this.muteScans(input.workspaceId);
      const releaseRepository = parent ? this.muteScans(parent.id) : undefined;
      try {
        const result = await executeUpdateWorktree({
          git: this.gitContext,
          repositoryPath: parent?.path ?? record.path,
          worktreePath: record.path,
          remote: input.remote,
          sourceRef: input.sourceRef,
          isActive: async () => (await this.countSessions(record.path)) > 0,
        });
        if (result.status === 'refused') {
          return err(
            result.reason === 'dirty'
              ? { type: 'worktree-dirty', workspaceId: input.workspaceId }
              : { type: 'workspace-active', workspaceId: input.workspaceId }
          );
        }
        if (result.status === 'diverged') {
          return err({ type: 'diverged', workspaceId: input.workspaceId, message: result.message });
        }
        if (result.status === 'failed') {
          return err({ type: 'stage-failed', stage: result.stage, message: result.message });
        }
        return ok(undefined);
      } finally {
        releaseRepository?.();
        releaseWorktree();
        this.settleScan({ kind: 'workspace', id: input.workspaceId, mode: 'full' });
      }
    });
  }

  /**
   * One autonomous ref-follow pass (spec: pr-workspace-model staleness, ref follow):
   * every follow-flagged, present worktree record fast-forwards to its durably
   * recorded fetch instruction — the ONE caller that reads `creation.gitSetup`, by
   * design (the manual verb takes instruction-as-input so pre-model workspaces work).
   * Every skip is a silent non-error retried on a later pass: dirty, active sessions,
   * diverged, and fetch failures (a closed PR's `refs/pull/N/head` may simply be
   * gone) all degrade to observation — nothing durable is written, no notice raised.
   * Sequential by design: a slow-cadence background pass never needs parallel
   * fetches, and one worktree at a time keeps the background-tier load trivial. A
   * registry with no flagged records makes this a cheap no-op — no git subprocess is
   * ever spawned. Returns pass counts for logging and structural test assertions.
   */
  async runRefFollowPass(): Promise<{ eligible: number; updated: number }> {
    const candidates = this.store
      .list()
      .filter(
        (record) =>
          record.kind === 'worktree' &&
          record.observedStatus === 'present' &&
          record.creation?.gitSetup?.followRef === true &&
          record.creation.gitSetup.fetchBranch !== undefined
      );
    let updated = 0;
    for (const candidate of candidates) {
      if (this.disposed) break;
      if (await this.followWorktree(candidate.id)) updated += 1;
    }
    if (updated > 0) {
      this.logger.info?.(`ref-follow pass moved ${updated} of ${candidates.length} checkouts`);
    }
    return { eligible: candidates.length, updated };
  }

  /**
   * One worktree's follow attempt, invoked exactly like the manual verb: the same
   * per-workspace claim (never two concurrent updates of one worktree), the same
   * watcher muting, the same shared executor (guards + ff-only under the writer
   * lock), the same trailing deliberate scan — a moved checkout surfaces only through
   * the normal observation path. Runs at the 'background' budget tier so follow work
   * never starves probes or creation. True only when the checkout actually moved.
   */
  private followWorktree(id: string): Promise<boolean> {
    return this.workspaceClaims.runExclusive(id, async () => {
      // Re-validated under the claim: the record may have changed since enumeration.
      const record = this.store.get(id);
      const instruction =
        record?.creation?.gitSetup?.followRef === true
          ? record.creation.gitSetup.fetchBranch
          : undefined;
      if (
        !record ||
        record.kind !== 'worktree' ||
        record.observedStatus !== 'present' ||
        instruction === undefined
      ) {
        return false;
      }
      const parent = record.parentId === null ? null : this.store.get(record.parentId);
      const releaseWorktree = this.muteScans(id);
      const releaseRepository = parent ? this.muteScans(parent.id) : undefined;
      try {
        const result = await executeUpdateWorktree({
          git: this.gitContext,
          repositoryPath: parent?.path ?? record.path,
          worktreePath: record.path,
          remote: instruction.remote,
          sourceRef: instruction.sourceRef,
          tier: 'background',
          isActive: async () => (await this.countSessions(record.path)) > 0,
        });
        if (result.status === 'updated') {
          this.logger.info?.(
            `ref-follow fast-forwarded '${id}' to ${instruction.sourceRef} (${result.toOid})`
          );
          return true;
        }
        if (result.status !== 'up-to-date') {
          // Forensic breadcrumb only — skips are ordinary, the next pass retries.
          this.logger.debug?.(`ref-follow skipped '${id}': ${describeSkip(result)}`);
        }
        return false;
      } finally {
        releaseRepository?.();
        releaseWorktree();
        this.settleScan({ kind: 'workspace', id, mode: 'full' });
      }
    });
  }

  /**
   * One plain RPC end-to-end: durable registration (outcome 'started') happens under
   * the writer queue; the long-running stage pipeline runs unserialized — concurrent
   * creations against one repository are safe (spec: git concurrency model) and the
   * repo-hold only keeps idle-gated scans away; the durable outcome lands under the
   * writer queue again. Progress is only visible through the records overlay.
   */
  async createWorktree(
    input: CreateWorktreeInput
  ): Promise<Result<WorkspaceRecord, CreateWorktreeError>> {
    const registration = await this.enqueue(() =>
      Promise.resolve(this.registerWorktreeCreation(input))
    );
    if (!registration.success) return registration;
    if (registration.data.execute === false) {
      return ok(this.toWire(registration.data.record));
    }
    const repository = registration.data.repository;

    const created = await this.gitContext.schedule.withRepoHold(repository.path, async () => {
      const startedAt = this.clock.now();
      const stageStarts: CreationStageTimeline = [];
      this.updateOverlay(input.workspaceId, (overlay) => ({
        ...overlay,
        creation: { stage: 'inspect', startedAt },
      }));
      stageStarts.push({ stage: 'inspect', at: Date.now() });

      const result = await executeCreateWorktree({
        git: this.gitContext,
        repositoryPath: repository.path,
        worktreePath: path.resolve(input.path),
        branch: input.branch,
        baseRef: input.baseRef ?? null,
        gitSetup: input.gitSetup,
        onStage: (stage) => {
          stageStarts.push({ stage, at: Date.now() });
          this.updateOverlay(input.workspaceId, (overlay) => ({
            ...overlay,
            creation: { stage, startedAt },
          }));
        },
      });
      this.logStageTimings(input.workspaceId, stageStarts, result.status);

      return await this.enqueue(() =>
        Promise.resolve(this.finalizeWorktreeCreation(input, result, stageStarts))
      );
    });

    // The verb returns at agent-spawnable; artifact cloning, branch pushing, and ref
    // freshening continue as durable background steps outside the repository claim.
    if (created.success) this.backgroundSteps.ensureRunning(input.workspaceId);
    return created;
  }

  refresh(input: RefreshWorkspacesInput): Promise<Result<void, WorkspaceNotFoundError>> {
    return this.executeRefresh(input);
  }

  async getProjectConfig(
    input: GetProjectConfigInput
  ): Promise<Result<ProjectConfigState, WorkspaceNotFoundError>> {
    await this.bootConfigHydration;
    const state = await this.resolveProjectConfigFor(input.workspaceId);
    return state ? ok(state) : err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
  }

  async refreshProjectConfig(
    input: GetProjectConfigInput
  ): Promise<Result<ProjectConfigState, WorkspaceNotFoundError>> {
    await this.bootConfigHydration;
    const projectRootId = await this.enqueue(async () => {
      const record = this.store.get(input.workspaceId);
      const projectRoot = record ? this.projectRootFor(record) : null;
      if (!record || !projectRoot || record.observedStatus !== 'present') return null;
      await this.refreshConfig(record.id, record.path);
      return projectRoot.id;
    });
    if (!projectRootId) {
      return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
    }
    await this.settleProjectConfigsForProjectRoot(projectRootId);
    const state = await this.resolveProjectConfigFor(input.workspaceId);
    return state ? ok(state) : err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
  }

  async patchPersonalProjectConfig(
    input: PatchPersonalProjectConfigInput
  ): Promise<Result<ProjectConfigState, WorkspaceNotFoundError>> {
    const projectRootId = await this.enqueue(() => {
      const record = this.store.get(input.workspaceId);
      const projectRoot = record ? this.projectRootFor(record) : null;
      if (!projectRoot) return null;
      const current = this.store.getPersonalConfig(projectRoot.id);
      const next = applyPersonalProjectConfigPatch(current, input);
      this.store.updatePersonalConfig(projectRoot.id, next);
      this.invalidateProjectConfigForProjectRoot(projectRoot.id);
      return projectRoot.id;
    });
    if (!projectRootId) {
      return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
    }
    await this.bootConfigHydration;
    await this.settleProjectConfigsForProjectRoot(projectRootId);
    const state = await this.resolveProjectConfigFor(input.workspaceId);
    return state ? ok(state) : err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
  }

  async importLegacyLifecycleSettings(
    input: ImportLegacyLifecycleSettingsInput
  ): Promise<Result<ProjectConfigState, WorkspaceNotFoundError>> {
    const projectRootId = await this.enqueue(() => {
      const record = this.store.get(input.workspaceId);
      const projectRoot = record ? this.projectRootFor(record) : null;
      if (!projectRoot) return null;
      if (!this.store.hasMigratedLegacyDesktopSettings(projectRoot.id)) {
        const current = this.store.getPersonalConfig(projectRoot.id);
        const next = applyLegacyLifecycleSettingsImport(current, input);
        this.store.importLegacyLifecycleSettings(projectRoot.id, next);
        this.invalidateProjectConfigForProjectRoot(projectRoot.id);
      }
      return projectRoot.id;
    });
    if (!projectRootId) {
      return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
    }
    await this.bootConfigHydration;
    const state = await this.resolveProjectConfigFor(input.workspaceId);
    return state ? ok(state) : err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
  }

  /** Host-settings live-state invalidation entry point used by the worker component. */
  hostSettingsChanged(): void {
    this.projectConfigPokes.poke({});
  }

  /**
   * On-demand git-aware disk observation; the path resolves from the registry's own
   * record. Runs off both lanes deliberately — a slow `du` over a large workspace must
   * never block mutations or scans, and it writes nothing.
   */
  async measureUsage(
    input: MeasureUsageInput,
    signal?: AbortSignal
  ): Promise<Result<WorkspaceUsage, MeasureUsageError>> {
    const record = this.store.get(input.workspaceId);
    if (!record) {
      return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
    }
    return measureWorkspaceUsage({ workspacePath: record.path, signal });
  }

  /**
   * Returns when prepare completes; setup/run continue in the background through the
   * activation manager. Held under the per-workspace claim so a concurrent deactivate
   * waits for the session-gating point instead of interleaving.
   */
  activateWorkspace(
    input: ActivateWorkspaceInput
  ): Promise<Result<WorkspaceRecord, ActivateWorkspaceError>> {
    return this.workspaceClaims.runExclusive(input.workspaceId, async () => {
      const record = this.store.get(input.workspaceId);
      if (!record) {
        return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
      }
      if (record.observedStatus === 'missing') {
        return err({ type: 'workspace-missing', workspaceId: input.workspaceId });
      }
      // Activation replays incomplete background steps (ticket semantics); the
      // activation manager's artifact gate awaits the copy only where scripts need it.
      if (hasIncompleteBackgroundSteps(record))
        this.backgroundSteps.ensureRunning(input.workspaceId);
      await this.activationManager.activate(input.workspaceId, record.path);
      const current = this.store.get(input.workspaceId) ?? record;
      return ok(this.toWire(current));
    });
  }

  /**
   * Sole owner of session-plane shutdown: cancels lifecycle runs first, runs teardown
   * when an activation exists, then kills every remaining session under the workspace
   * path (including never-activated workspaces). Idempotent: teardown runs at most once.
   */
  deactivateWorkspace(
    input: DeactivateWorkspaceInput
  ): Promise<Result<void, WorkspaceNotFoundError>> {
    return this.workspaceClaims.runExclusive(input.workspaceId, async () => {
      const record = this.store.get(input.workspaceId);
      if (!record) {
        return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
      }
      await this.deactivateLocked(record);
      return ok(undefined);
    });
  }

  /** The shared deactivation step; callers must hold the per-workspace claim. */
  private async deactivateLocked(
    record: DurableWorkspaceRecord
  ): Promise<WorkspaceDeactivationResult> {
    // Stop and await script-plane runs first. Killing their terminal sessions first
    // can make an intentional Stop look like a failed process exit.
    const deactivation = await this.activationManager.deactivate(record.id);
    try {
      await this.killSessions(record.path);
    } catch (error) {
      // Best-effort by contract: teardown must still run.
      this.logger.warn?.(`session cleanup for '${record.path}' failed`, { error });
    }
    return deactivation;
  }

  /**
   * The delete verbs' deactivation step: a failed teardown counts as a removal stage
   * (ADR 0006) — recorded durably before the verb returns. Transient by design:
   * teardown runs at most once per activation, so the next attempt proceeds past it.
   */
  private async deactivateForRemoval(
    record: DurableWorkspaceRecord
  ): Promise<DeleteWorkspaceError | null> {
    const { teardownFailure } = await this.deactivateLocked(record);
    if (!teardownFailure) return null;
    return await this.recordRemovalFailure(record.id, {
      stage: 'teardown',
      class: 'transient',
      message: teardownFailure.message,
    });
  }

  /**
   * Durable half of a failed removal: the annotation lands on the record (and the
   * records live model) before the verb returns; the returned error is loop control
   * carrying the same host-decided stage/class facts as the record — nothing the
   * record does not (ADR 0006).
   */
  private async recordRemovalFailure(
    id: string,
    failure: Omit<WorkspaceRemovalAttempt, 'at'>
  ): Promise<DeleteWorkspaceError> {
    await this.enqueue(async () => {
      const record = this.store.get(id);
      if (!record) return;
      const now = this.clock.now();
      const updated: DurableWorkspaceRecord = {
        ...record,
        lastRemovalAttempt: { ...failure, at: now },
        updatedAt: now,
      };
      this.store.update(updated);
      this.publish(updated);
    });
    return {
      type: 'remove-failed',
      stage: failure.stage,
      class: failure.class,
      message: failure.message,
    };
  }

  /** The parent record's path when it is usable, else what the disk says. */
  private async resolveRepositoryPath(
    record: DurableWorkspaceRecord,
    parent: DurableWorkspaceRecord | null
  ): Promise<string | null> {
    if (parent && (await isDirectory(parent.path))) return parent.path;
    const inspection = await this.inspector(record.path);
    return inspection.kind === 'worktree' ? inspection.repositoryPath : null;
  }

  /** Scheduler entry point; the pass bodies live on the scanner. */
  executeScanRequest(request: ScanRequest): Promise<void> {
    return this.scanner.executeScanRequest(request);
  }

  /** The scheduler's view of the registry: present paths to watch, staleness to bound. */
  scanTargets(): ScanTarget[] {
    return this.store.list().map((record) => ({
      id: record.id,
      kind: record.kind,
      path: record.path,
      parentId: record.parentId,
      gitAdminName: record.gitAdminName,
      observedStatus: record.observedStatus,
      lastObservedAt: record.lastObservedAt,
    }));
  }

  /** Activity escalation gate: activated workspaces (or fresh activations) scan eagerly. */
  isWorkspaceActive(id: string): boolean {
    const overlay = this.overlays.get(id);
    if (overlay?.activation) return true;
    const record = this.store.get(id);
    if (!record || record.lastActivatedAt === null) return false;
    return this.clock.now() - record.lastActivatedAt < 60 * 60_000;
  }

  private async createWorkspaceLocked(
    input: CreateWorkspaceInput
  ): Promise<Result<WorkspaceRecord, CreateWorkspaceError>> {
    await this.bootConfigHydration;
    const canonical = await canonicalizeWorkspacePath(input.path);
    if (canonical === null) {
      return err({ type: 'path-not-found', path: input.path });
    }

    const existing = this.store.get(input.workspaceId);
    if (existing) {
      if (existing.path === canonical) {
        // Idempotent replay: same id, same path — no-op success.
        return ok(this.toWire(existing));
      }
      return err({
        type: 'immutable-field-mismatch',
        workspaceId: input.workspaceId,
        message: `Workspace '${input.workspaceId}' is registered at '${existing.path}', not '${canonical}'`,
      });
    }

    const byPath = this.store.getByPath(canonical);
    if (byPath) {
      // The Host owns path identity: a second desktop consumes the canonical record.
      return ok(this.toWire(byPath));
    }

    const inspection = await this.inspector(canonical);
    if (inspection.kind === 'inspect-failed') {
      return err({ type: 'inspect-failed', path: canonical, message: inspection.message });
    }

    const now = this.clock.now();
    let parentId: string | null = null;
    let gitAdminName: string | null = null;
    if (inspection.kind === 'worktree') {
      parentId = await this.ensureRepositoryRegistered(inspection.repositoryPath, now);
      gitAdminName = inspection.gitAdminName;
    }

    const record: DurableWorkspaceRecord = {
      id: input.workspaceId,
      kind: inspection.kind,
      path: canonical,
      parentId,
      origin: 'registered',
      gitAdminName,
      observedStatus: 'present',
      creation: null,
      lastCreateOutcome: null,
      lifecycle: null,
      lastRemovalAttempt: null,
      git: null,
      lastActivatedAt: null,
      createdAt: now,
      updatedAt: now,
      lastObservedAt: now,
    };
    await this.refreshConfig(record.id, record.path);
    this.store.insert(record);
    this.publish(record);
    return ok(this.toWire(record));
  }

  /** Late-bound because the scheduler needs the runtime before it can be pointed at. */
  setOnRecordsChanged(callback: () => void): void {
    this.onRecordsChanged = callback;
  }

  /** Late-bound scheduler mute seam; same lifecycle as setOnRecordsChanged. */
  setScanMuter(muter: (id: string) => () => void): void {
    this.muteScans = muter;
  }

  /**
   * The fast durable half of createWorktree: the record exists with outcome 'started'
   * before any git work begins, so a crash mid-flight leaves a visible, retryable fact.
   */
  private registerWorktreeCreation(
    input: CreateWorktreeInput
  ): Result<
    { execute: boolean; record: DurableWorkspaceRecord; repository: DurableWorkspaceRecord },
    CreateWorktreeError
  > {
    const repository = this.store.get(input.repositoryId);
    if (!repository || repository.kind !== 'repository') {
      return err({ type: 'repository-not-found', repositoryId: input.repositoryId });
    }

    const now = this.clock.now();
    const existing = this.store.get(input.workspaceId);
    if (existing) {
      const spec = existing.creation;
      const matches =
        spec !== null &&
        spec.branch === input.branch &&
        spec.baseRef === (input.baseRef ?? null) &&
        sameGitSetup(spec.gitSetup, input.gitSetup) &&
        spec.requestedPath === input.path &&
        existing.parentId === input.repositoryId;
      if (!matches) {
        return err({
          type: 'immutable-field-mismatch',
          workspaceId: input.workspaceId,
          message: `Workspace '${input.workspaceId}' exists with a different creation spec`,
        });
      }
      if (existing.lastCreateOutcome?.status === 'succeeded') {
        // Replay of a completed creation: no-op foreground success; incomplete
        // background steps re-run through the caller's post-verb kickoff.
        return ok({ execute: false, record: existing, repository });
      }
      // Failed or interrupted: re-execute under a fresh 'started' outcome. The
      // lifecycle section clears — the fresh attempt writes its own steps at finalize.
      const restarted: DurableWorkspaceRecord = {
        ...existing,
        lastCreateOutcome: { status: 'started', at: now },
        lifecycle: null,
        updatedAt: now,
      };
      this.store.update(restarted);
      this.publish(restarted);
      return ok({ execute: true, record: restarted, repository });
    }

    const resolvedPath = path.resolve(input.path);
    const byPath = this.store.getByPath(resolvedPath);
    if (byPath) {
      return err({ type: 'path-conflict', path: resolvedPath });
    }

    const record: DurableWorkspaceRecord = {
      id: input.workspaceId,
      kind: 'worktree',
      path: resolvedPath,
      parentId: repository.id,
      origin: 'registered',
      gitAdminName: null,
      // Not on disk yet: 'missing' + outcome 'started' + no overlay reads as
      // "interrupted" after a daemon crash — exactly the diagnostic the spec wants.
      observedStatus: 'missing',
      creation: {
        branch: input.branch,
        baseRef: input.baseRef ?? null,
        requestedPath: input.path,
        ...(input.gitSetup !== undefined ? { gitSetup: input.gitSetup } : {}),
      },
      lastCreateOutcome: { status: 'started', at: now },
      lifecycle: null,
      lastRemovalAttempt: null,
      git: null,
      lastActivatedAt: null,
      createdAt: now,
      updatedAt: now,
      lastObservedAt: now,
    };
    this.store.insert(record);
    this.publish(record);
    return ok({ execute: true, record, repository });
  }

  /** The durable tail of createWorktree: outcome lands, overlay clears, record settles. */
  private async finalizeWorktreeCreation(
    input: CreateWorktreeInput,
    result: Awaited<ReturnType<typeof executeCreateWorktree>>,
    stages: CreationStageTimeline
  ): Promise<Result<WorkspaceRecord, CreateWorktreeError>> {
    const id = input.workspaceId;
    this.updateOverlay(id, (overlay) => ({ ...overlay, creation: null }));
    const record = this.store.get(id);
    const now = this.clock.now();
    if (!record) {
      // Deleted while the pipeline ran; report the execution result without a record.
      return err({
        type: 'stage-failed',
        stage: 'finalize',
        message: 'Workspace record was deleted during creation',
      });
    }

    // Every settled pipeline writes its lifecycle facts — success and failure alike;
    // the failed step carries the stage's message for the Activity timeline. Artifact
    // patterns use the same personal > team > built-in resolution as the settings UI.
    // The legacy request field remains wire-compatible but is no longer a config layer.
    await this.bootConfigHydration;
    const sourceConfig = await this.resolveProjectConfigFor(input.repositoryId);
    const preservePatterns = [...(sourceConfig?.resolved.preservePatterns.value ?? [])];
    const lifecycle = buildCreationLifecycle({ ...input, preservePatterns }, result, stages, now);

    if (result.status === 'failed') {
      const failed: DurableWorkspaceRecord = {
        ...record,
        lastCreateOutcome: {
          status: 'failed',
          at: now,
          stage: result.stage,
          message: result.message,
        },
        lifecycle,
        updatedAt: now,
      };
      this.store.update(failed);
      this.publish(failed);
      return err({ type: 'stage-failed', stage: result.stage, message: result.message });
    }

    const parent = record.parentId === null ? null : this.store.get(record.parentId);
    let gitAdminName = record.gitAdminName;
    if (parent) {
      try {
        const listing = (await listRepositoryWorktrees(this.gitContext, parent.path)).find(
          (entry) => entry.path === result.finalPath
        );
        gitAdminName = listing?.adminName ?? gitAdminName;
      } catch {
        // The scan will fill the admin name on its next pass.
      }
    }
    const succeeded: DurableWorkspaceRecord = {
      ...record,
      path: result.finalPath,
      gitAdminName,
      observedStatus: 'present',
      lifecycle,
      lastCreateOutcome: { status: 'succeeded', at: now },
      git: await observeWorkspaceGit(this.gitContext, result.finalPath, undefined, {
        // The scanner's cache, borrowed: the first scan after this creation stays warm.
        untrackedCache: this.scanner.untrackedCacheFor(record.id),
      }),
      updatedAt: now,
      lastObservedAt: now,
    };
    await this.refreshConfig(succeeded.id, succeeded.path);
    this.store.update(succeeded);
    this.publish(succeeded);
    return ok(this.toWire(succeeded));
  }

  /**
   * The deliberate trailing scan after a self-suppressed write settles (spec: scan
   * minimization): fire-and-forget so the step never blocks on scan-lane time.
   */
  private settleScan(request: ScanRequest): void {
    if (this.disposed) return;
    void this.scanner.executeScanRequest(request).catch((error) => {
      this.logger.warn?.(`settle scan for '${request.id}' failed`, { error });
    });
  }

  /**
   * Manual retry of a durably failed lifecycle step. 'failed' is the only status a
   * retry re-runs; anything else (succeeded, skipped, or an in-flight run the retry
   * waits out) is a no-op returning the current record.
   */
  async retryStep(input: RetryStepInput): Promise<Result<WorkspaceRecord, WorkspaceNotFoundError>> {
    const record = this.store.get(input.workspaceId);
    if (!record) {
      return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
    }
    await this.backgroundSteps.retry(input.workspaceId, input.step);
    const current = this.store.get(input.workspaceId) ?? record;
    return ok(this.toWire(current));
  }

  /**
   * Manual/retry script run, brokered here so the request is host-built: facts from
   * the record, the standard 5-minute timeout for everything but run. The run is
   * detached — this verb returns once it started; observation writes its steps.
   */
  async runScript(input: RunScriptInput): Promise<Result<void, RunScriptError>> {
    const record = this.store.get(input.workspaceId);
    if (!record) {
      return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
    }
    if (!this.scriptsClient) {
      return err({ type: 'spawn-failed', message: 'No scripts runtime is available on this host' });
    }
    const facts = await this.scriptFactsFor(record.path);
    await this.bootConfigHydration;
    const resolved = await this.resolveProjectConfigFor(record.id);
    const command = resolved?.resolved[input.script]?.value;
    if (!command) {
      return err({
        type: 'script-not-configured',
        message: `No '${input.script}' script is configured for this workspace`,
      });
    }
    const started = await this.scriptsClient.start({
      workspacePath: record.path,
      script: input.script,
      provenance: input.provenance,
      facts,
      command,
      shellSetup: resolved?.resolved.shellSetup?.value ?? '',
      // Run scripts are dev-server-shaped: no timeout; everything else gets the
      // same 5-minute box activation applies.
      ...(input.script === 'run' ? {} : { timeoutMs: DEFAULT_SCRIPT_TIMEOUT_MS }),
    });
    if (!started.success) return err(started.error);
    return ok(undefined);
  }

  /**
   * Durable step writer; publishing folds the change into the records overlay.
   * 'running' stamps startedAt; terminal statuses stamp finishedAt (skips that never
   * started keep startedAt null).
   */
  private updateLifecycleStep(
    id: string,
    stepId: WorkspaceLifecycleStepId,
    state: {
      status: WorkspaceLifecycleStep['status'];
      message?: string;
      params?: WorkspaceLifecycleStep['params'];
    }
  ): Promise<void> {
    return this.enqueue(async () => {
      const record = this.store.get(id);
      if (!record) return;
      // Script runs can land on records with no creation history (adopted worktrees,
      // manual runs before any activation): mint the section rather than drop the run.
      const lifecycle = record.lifecycle ?? { steps: [], preservePatterns: [] };
      const now = this.clock.now();
      const previous = getLifecycleStep(lifecycle, stepId);
      const terminal = state.status !== 'pending' && state.status !== 'running';
      const step: WorkspaceLifecycleStep = {
        id: stepId,
        status: state.status,
        startedAt: state.status === 'running' ? now : (previous?.startedAt ?? null),
        finishedAt: terminal ? now : null,
        ...(state.message !== undefined ? { message: state.message } : {}),
        params: state.params ?? previous?.params ?? {},
      };
      const updated: DurableWorkspaceRecord = {
        ...record,
        lifecycle: withLifecycleStep(lifecycle, step),
        updatedAt: now,
      };
      this.store.update(updated);
      this.publish(updated);
    });
  }

  /**
   * The observation stream's landing point (spec: observation is the single
   * step-writer): every scripts-runtime run transition — activation, manual, or
   * retry — mirrors into the durable lifecycle step for that script. Timed-out runs
   * settle the step as failed with the timeout message; failure messages fold in the
   * run's output tail.
   */
  private onScriptRun(run: ObservedScriptRun): void {
    const record = this.store.getByPath(run.workspacePath);
    if (!record) return;
    const params = { provenance: run.provenance };
    const state =
      run.status === 'running'
        ? { status: 'running' as const, params }
        : run.status === 'succeeded'
          ? { status: 'succeeded' as const, params }
          : run.status === 'cancelled'
            ? { status: 'cancelled' as const, message: run.message ?? 'Stopped', params }
            : {
                status: 'failed' as const,
                message: failureMessageWithTail(
                  run.message ?? `Script '${run.script}' failed`,
                  run.outputTail
                ),
                params,
              };
    void this.updateLifecycleStep(record.id, run.script, state).catch((error) => {
      this.logger.warn?.(`recording observed ${run.script} run for '${record.id}' failed`, {
        error,
      });
    });
  }

  /** Record facts for the script env builder — same derivations for every initiator. */
  private async scriptFactsFor(workspacePath: string): Promise<ScriptWorkspaceFacts> {
    const record = this.store.getByPath(workspacePath);
    if (!record) return { workspaceId: workspacePath };
    const parent = record.parentId === null ? null : this.store.get(record.parentId);
    const repositoryPath = await this.resolveRepositoryPath(record, parent);
    const branch = record.git?.branch ?? record.creation?.branch;
    // 'origin/main' → 'main': EMDASH_DEFAULT_BRANCH is a branch name, not a ref.
    const baseRef = record.creation?.baseRef;
    const defaultBranch = baseRef?.includes('/')
      ? baseRef.slice(baseRef.indexOf('/') + 1)
      : baseRef;
    return {
      workspaceId: record.id,
      ...(repositoryPath !== null ? { repositoryPath } : {}),
      ...(branch ? { branch } : {}),
      ...(defaultBranch ? { defaultBranch } : {}),
    };
  }

  /** Points the run observer at every present record path; called on records changes. */
  private syncScriptObservers(): void {
    if (!this.scriptRuns || this.disposed) return;
    const paths = new Set<string>();
    for (const record of this.store.list()) {
      if (record.observedStatus === 'present') paths.add(record.path);
    }
    this.scriptRuns.sync(paths);
  }

  /**
   * Boot settlement: script runs died with the previous daemon, so steps left
   * pending/running settle as cancelled — the timeline never lies about an in-flight
   * run that no longer exists.
   */
  private settleInterruptedScriptSteps(record: DurableWorkspaceRecord): void {
    for (const step of record.lifecycle?.steps ?? []) {
      if (!SCRIPT_STEP_IDS.has(step.id)) continue;
      if (step.status !== 'pending' && step.status !== 'running') continue;
      void this.updateLifecycleStep(record.id, step.id, {
        status: 'cancelled',
        message: 'Interrupted by restart',
      }).catch((error) => {
        this.logger.warn?.(`settling interrupted ${step.id} step for '${record.id}' failed`, {
          error,
        });
      });
    }
  }

  private logStageTimings(
    id: string,
    stageStarts: Array<{ stage: string; at: number }>,
    status: string
  ): void {
    const durations: Record<string, number> = {};
    const end = Date.now();
    for (let index = 0; index < stageStarts.length; index += 1) {
      const next = index + 1 < stageStarts.length ? stageStarts[index + 1]!.at : end;
      durations[stageStarts[index]!.stage] = next - stageStarts[index]!.at;
    }
    const total = stageStarts.length > 0 ? end - stageStarts[0]!.at : 0;
    this.logger.info?.(`createWorktree '${id}' ${status} in ${total}ms`, { stages: durations });
  }

  /** Overlay writes republish the merged record; an all-empty overlay reads as null. */
  private updateOverlay(
    id: string,
    mutate: (overlay: WorkspaceRuntimeOverlay) => WorkspaceRuntimeOverlay
  ): void {
    const current = this.overlays.get(id) ?? { creation: null, notices: [], activation: null };
    const next = mutate(current);
    if (next.creation === null && next.activation === null && next.notices.length === 0) {
      this.overlays.delete(id);
    } else {
      this.overlays.set(id, next);
    }
    const record = this.store.get(id);
    if (record) this.publish(record);
  }

  private deleteWorkspaceLocked(input: DeleteWorkspaceInput): Result<void, DeleteWorkspaceError> {
    const existing = this.store.get(input.workspaceId);
    const projectRoot = existing ? this.projectRootFor(existing) : null;
    const deleted = this.store.delete(input.workspaceId);
    if (deleted) {
      this.overlays.delete(input.workspaceId);
      this.scanner.evict(input.workspaceId);
      this.configs.delete(input.workspaceId);
      this.recordsCell.update((previous) => {
        const next = { ...previous };
        delete next[input.workspaceId];
        return next;
      });
      this.syncScriptObservers();
      this.onRecordsChanged?.();
      if (projectRoot && existing) {
        this.invalidateProjectConfigForMembershipChange(projectRoot.id, [existing.id]);
      }
    } else {
      this.logger.debug?.(`delete of absent workspace '${input.workspaceId}' — idempotent no-op`);
    }
    return ok(undefined);
  }

  // -------------------------------------------------------------------------
  // Scan landings: the pass bodies live on the scanner (scan/scanner.ts); what
  // lands here is re-validated against the live store on the mutation lane.
  // -------------------------------------------------------------------------

  /**
   * The refresh verb's body; the scans run on the scanner's lane, and existence is
   * judged there too — a record deleted while earlier scans drain reads as not found,
   * exactly as it did before the extraction.
   */
  private async executeRefresh(
    input: RefreshWorkspacesInput
  ): Promise<Result<void, WorkspaceNotFoundError>> {
    if (input.workspaceId !== undefined) {
      const scanned = await this.scanner.scanRecord(input.workspaceId);
      if (!scanned) {
        return err({ type: 'workspace-not-found', workspaceId: input.workspaceId });
      }
      return ok(undefined);
    }
    await this.scanner.scanHost();
    return ok(undefined);
  }

  scanHost(): Promise<void> {
    return this.scanner.scanHost();
  }

  /**
   * Lands one scan observation on the mutation lane, re-validated against the live
   * store: a record deleted while the observation ran stays deleted — the scan never
   * resurrects it (spec: scan lane with re-validated landings).
   */
  private applyObservation(
    id: string,
    patch: Partial<DurableWorkspaceRecord>,
    now: number
  ): Promise<void> {
    return this.enqueue(() => {
      const current = this.store.get(id);
      if (!current) return;
      this.saveRecord({ ...current, ...patch } as DurableWorkspaceRecord, now);
    });
  }

  /** The vanished landing, re-validated like {@link applyObservation}. */
  private applyVanished(id: string, now: number): Promise<void> {
    return this.enqueue(() => {
      const current = this.store.get(id);
      if (!current) return;
      this.recordVanished(current, now);
    });
  }

  /** Adoption landing; false when the id or path got claimed while the scan observed. */
  private async applyAdoption(adopted: DurableWorkspaceRecord): Promise<boolean> {
    if (this.store.get(adopted.id) || this.store.getByPath(adopted.path)) return false;
    await this.refreshConfig(adopted.id, adopted.path);
    const accepted = await this.enqueue(() => {
      if (this.store.get(adopted.id)) return false;
      if (this.store.getByPath(adopted.path)) return false;
      this.store.insert(adopted);
      this.publish(adopted);
      return true;
    });
    if (!accepted) this.configs.delete(adopted.id);
    return accepted;
  }

  /** Adopted records follow the disk; registered records survive as 'missing'. Mutation-lane only. */
  private recordVanished(record: DurableWorkspaceRecord, now: number): void {
    this.scanner.evict(record.id);
    this.configs.delete(record.id);
    if (record.origin === 'adopted') {
      this.deleteWorkspaceLocked({ workspaceId: record.id });
      return;
    }
    this.saveRecord({ ...record, observedStatus: 'missing', git: null }, now);
  }

  /**
   * (Re)reads one workspace's `.hardcore.json` into the live model. Runs at boot, at
   * creation finalize/adoption, and on full scans (the working-tree watchers feed
   * those) — the blocking creation/activation paths only ever read the map. A parse
   * failure degrades to the empty config plus a visible notice; a change republishes
   * the record so the wire summary stays fresh.
   */
  private refreshConfig(id: string, workspacePath: string): Promise<WorkspaceConfigEntry> {
    return this.configs.refresh(id, workspacePath);
  }

  private async hydrateBootConfigs(): Promise<void> {
    await Promise.all(
      this.store
        .list()
        .filter((record) => record.observedStatus === 'present')
        .map(async (record) => {
          try {
            await this.refreshConfig(record.id, record.path);
          } catch (error) {
            this.logger.warn?.(`boot config hydration for '${record.path}' failed`, { error });
          }
        })
    );
  }

  private async resolveProjectConfigFor(id: string): Promise<ProjectConfigState | null> {
    const record = this.store.get(id);
    if (!record) return null;
    const repository = this.projectRootFor(record);
    if (!repository) return null;
    const projectRecords = this.store
      .list()
      .filter(
        (candidate) => candidate.id === repository.id || candidate.parentId === repository.id
      );
    const entry = this.configs.get(record.id);
    const personalConfig = this.store.getPersonalConfig(repository.id);
    const resolved = resolveProjectConfig({
      personalConfig,
      workspaceConfig: entry?.config ?? {},
      hostSettings: await this.getHostSettings(),
    });
    return {
      workspaceId: record.id,
      repositoryId: repository.id,
      ...resolved,
      personalConfig,
      sources: collectProjectConfigSources(projectRecords, this.configs),
      legacyDesktopSettingsMigrated: this.store.hasMigratedLegacyDesktopSettings(repository.id),
    };
  }

  private async settleProjectConfigsForProjectRoot(projectRootId: string): Promise<void> {
    await Promise.all(
      this.store
        .list()
        .filter((record) => record.id === projectRootId || record.parentId === projectRootId)
        .map(async (record) => {
          const query = this.projectConfigs.peekMember({ workspaceId: record.id });
          if (!query) return;
          const state = await this.resolveProjectConfigFor(record.id);
          if (state) query.settle(state);
        })
    );
  }

  private repositoryRecordFor(record: DurableWorkspaceRecord): DurableWorkspaceRecord | null {
    if (record.kind === 'repository') return record;
    if (record.kind !== 'worktree' || record.parentId === null) return null;
    const parent = this.store.get(record.parentId);
    return parent?.kind === 'repository' ? parent : null;
  }

  private projectRootFor(record: DurableWorkspaceRecord): DurableWorkspaceRecord | null {
    if (record.kind === 'directory') return record;
    return this.repositoryRecordFor(record);
  }

  private invalidateProjectConfigForProjectRoot(
    projectRootId: string,
    additionalWorkspaceIds: readonly string[] = []
  ): void {
    const workspaceIds = new Set(additionalWorkspaceIds);
    for (const record of this.store.list()) {
      if (record.id === projectRootId || record.parentId === projectRootId) {
        workspaceIds.add(record.id);
      }
    }
    this.projectConfigPokes.poke({
      workspaceIds: [...workspaceIds],
    });
  }

  private invalidateProjectConfigForMembershipChange(
    projectRootId: string,
    additionalWorkspaceIds: readonly string[] = []
  ): void {
    const next = this.projectMembershipFingerprint(projectRootId);
    if (this.projectMembershipFingerprints.get(projectRootId) === next) return;
    if (next === '[]') this.projectMembershipFingerprints.delete(projectRootId);
    else this.projectMembershipFingerprints.set(projectRootId, next);
    this.invalidateProjectConfigForProjectRoot(projectRootId, additionalWorkspaceIds);
  }

  private projectMembershipFingerprint(projectRootId: string): string {
    return stableStringify(
      this.store
        .list()
        .filter((record) => record.id === projectRootId || record.parentId === projectRootId)
        .map((record) => ({ id: record.id, parentId: record.parentId, path: record.path }))
        .sort((left, right) => (left.id < right.id ? -1 : left.id > right.id ? 1 : 0))
    );
  }

  /** Side effects of a config change; cache discipline lives in the shared model. */
  private onConfigChanged(
    id: string,
    entry: WorkspaceConfigEntry,
    previous: WorkspaceConfigEntry | undefined,
    workspacePath: string
  ): void {
    const record = this.store.get(id);
    if (entry.parseError !== (previous?.parseError ?? false)) {
      this.updateOverlay(id, (overlay) => ({
        ...overlay,
        notices: [
          ...overlay.notices.filter((notice) => notice.id !== 'config-invalid'),
          ...(entry.parseError
            ? [
                {
                  id: 'config-invalid',
                  kind: 'config-invalid' as const,
                  message: `Could not parse .hardcore.json in '${workspacePath}'; using defaults`,
                  at: this.clock.now(),
                },
              ]
            : []),
        ],
      }));
    } else if (record) {
      this.publish(record);
    }
    const projectRoot = record ? this.projectRootFor(record) : null;
    if (projectRoot) this.invalidateProjectConfigForProjectRoot(projectRoot.id);
  }

  /** Persists a scan result, stamping observation time and bumping updatedAt on change. */
  private saveRecord(next: DurableWorkspaceRecord, now: number): void {
    const previous = this.store.get(next.id);
    const changed = !previous || !sameRecordEssence(previous, next);
    const record: DurableWorkspaceRecord = {
      ...next,
      updatedAt: changed ? now : (previous?.updatedAt ?? now),
      lastObservedAt: now,
    };
    this.store.update(record);
    this.publish(record);
  }

  /**
   * Registering a worktree of an unregistered repository auto-registers the parent as
   * adopted (host-minted id) so `parentId` always resolves.
   */
  private async ensureRepositoryRegistered(repositoryPath: string, now: number): Promise<string> {
    const existing = this.store.getByPath(repositoryPath);
    if (existing) return existing.id;

    const parent: DurableWorkspaceRecord = {
      id: crypto.randomUUID(),
      kind: 'repository',
      path: repositoryPath,
      parentId: null,
      origin: 'adopted',
      gitAdminName: null,
      observedStatus: 'present',
      creation: null,
      lastCreateOutcome: null,
      lifecycle: null,
      lastRemovalAttempt: null,
      git: null,
      lastActivatedAt: null,
      createdAt: now,
      updatedAt: now,
      lastObservedAt: now,
    };
    await this.refreshConfig(parent.id, parent.path);
    this.store.insert(parent);
    this.publish(parent);
    return parent.id;
  }

  private enqueue<T>(operation: () => Promise<T> | T): Promise<T> {
    const next = this.mutationQueue.then(operation, operation);
    this.mutationQueue = next.catch(() => undefined);
    return next;
  }

  private publish(record: DurableWorkspaceRecord): void {
    const wire = this.toWire(record);
    this.recordsCell.update((previous) => ({ ...previous, [record.id]: wire }));
    const projectRoot = this.projectRootFor(record);
    if (projectRoot) this.invalidateProjectConfigForMembershipChange(projectRoot.id);
    this.syncScriptObservers();
    this.onRecordsChanged?.();
  }

  private toWire(record: DurableWorkspaceRecord): WorkspaceRecord {
    const overlay = this.overlays.get(record.id);
    const configEntry = this.configs.get(record.id);
    const config = configEntry
      ? {
          scripts: {
            prepare: configEntry.config.scripts?.prepare !== undefined,
            setup: configEntry.config.scripts?.setup !== undefined,
            run: configEntry.config.scripts?.run !== undefined,
            teardown: configEntry.config.scripts?.teardown !== undefined,
          },
          preservePatterns: configEntry.config.preservePatterns ?? [],
          parseError: configEntry.parseError,
        }
      : null;
    // The durable lifecycle section rides the overlay so clients keep one progress
    // surface; unlike the rest of the overlay it survives daemon restarts. While the
    // foreground pipeline runs, its current stage rides along as a synthetic running
    // step so the timeline is live before any durable step lands.
    let lifecycle = record.lifecycle?.steps ?? null;
    if (overlay?.creation) {
      const running: WorkspaceLifecycleStep = {
        id: stepIdForStage(overlay.creation.stage),
        status: 'running',
        startedAt: overlay.creation.startedAt,
        finishedAt: null,
        params: record.creation
          ? {
              branch: record.creation.branch,
              ...(record.creation.baseRef !== null ? { base: record.creation.baseRef } : {}),
              path: record.creation.requestedPath,
            }
          : {},
      };
      lifecycle = [...(lifecycle ?? []).filter((step) => step.id !== running.id), running];
    }
    const runtime =
      overlay !== undefined || lifecycle !== null
        ? {
            creation: overlay?.creation ?? null,
            notices: overlay?.notices ?? [],
            activation: overlay?.activation ?? null,
            lifecycle,
          }
        : null;
    return { ...record, config, runtime };
  }
}

function hasIncompleteBackgroundSteps(record: DurableWorkspaceRecord): boolean {
  const lifecycle = record.lifecycle;
  if (!lifecycle || record.lastCreateOutcome?.status !== 'succeeded') return false;
  return BACKGROUND_STEP_IDS.some((id) => isIncompleteStep(getLifecycleStep(lifecycle, id)));
}

/** The skip's one-line forensic description for the follow pass's debug log. */
function describeSkip(result: UpdateWorktreeExecutionResult): string {
  switch (result.status) {
    case 'refused':
      return result.reason;
    case 'diverged':
      return 'diverged';
    case 'failed':
      return `${result.stage} failed: ${result.message}`;
    default:
      return result.status;
  }
}

/**
 * Replay-identity comparison of two gitSetup blocks, key-order independent: durable
 * records round-trip through JSON, so a field-by-field canonical form is compared
 * instead of the raw objects.
 */
function sameGitSetup(a?: WorkspaceGitSetup, b?: WorkspaceGitSetup): boolean {
  const canonical = (setup?: WorkspaceGitSetup) =>
    setup === undefined
      ? null
      : {
          fetchBranch: setup.fetchBranch
            ? { remote: setup.fetchBranch.remote, sourceRef: setup.fetchBranch.sourceRef }
            : null,
          upstream: setup.upstream
            ? { remote: setup.upstream.remote, mergeRef: setup.upstream.mergeRef }
            : null,
          breadcrumb: setup.breadcrumb ? { prUrl: setup.breadcrumb.prUrl } : null,
          followRef: setup.followRef ?? null,
        };
  return JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
}

/** The change-detection view of a record: everything except the bookkeeping stamps. */
function recordEssence(
  record: DurableWorkspaceRecord
): Omit<DurableWorkspaceRecord, 'updatedAt' | 'lastObservedAt'> {
  const { updatedAt: _updatedAt, lastObservedAt: _lastObservedAt, ...essence } = record;
  return essence;
}

/**
 * Key-order-independent equality of two records' change-detection essence: a stored
 * record round-trips through JSON in zod parse order while a scan result is built as
 * a literal, so key order must never masquerade as a change (the {@link sameGitSetup}
 * precedent). Exported for saveRecord's unit test only.
 */
export function sameRecordEssence(a: DurableWorkspaceRecord, b: DurableWorkspaceRecord): boolean {
  return stableStringify(recordEssence(a)) === stableStringify(recordEssence(b));
}

async function isDirectory(path: string): Promise<boolean> {
  try {
    return (await fs.stat(path)).isDirectory();
  } catch {
    return false;
  }
}
