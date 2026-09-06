import crypto from 'node:crypto';
import { promises as fs } from 'node:fs';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import type { WorkspaceGitObservations } from '../../api/schemas';
import type { RegistryGitContext } from '../git-context';
import type { DurableWorkspaceRecord } from '../persistence/record-store';
import {
  createRemoteUrlCache,
  createUntrackedLinesCache,
  listRepositoryWorktrees,
  observeWorkspaceGit,
  observeWorkspaceGitRefs,
  type ObserveWorkspaceGitOptions,
  type ObserveWorkspaceGitRefsOptions,
  type UntrackedLinesCache,
  type WorktreeListing,
} from './observe-git';
import type { ScanRequest } from './scheduler';

/**
 * The scanner's whole view of the registry (spec: registry-runtime-carveout, scan
 * plane): queries plus re-validated landings, implemented by the runtime. Landings
 * run on the runtime's mutation lane, re-validated against the live store — the
 * never-resurrect guard and ADR 0001's positive-assertion invariant stay structural
 * on the runtime side of this port. No store, no mutation queue, no publish crosses
 * the seam.
 */
export type ScanLanding = {
  get(id: string): DurableWorkspaceRecord | undefined;
  list(): DurableWorkspaceRecord[];
  /** Patch one record's observation columns. A record deleted mid-scan stays deleted. */
  observation(id: string, patch: Partial<DurableWorkspaceRecord>, now: number): Promise<void>;
  /** Adopted records follow the disk (deleted); registered records survive as missing. */
  vanished(id: string, now: number): Promise<void>;
  /** False when the id or path got claimed while the scan observed. */
  adoption(record: DurableWorkspaceRecord): Promise<boolean>;
  refreshConfig(id: string, path: string): Promise<void>;
};

/** The observation seam: tests inject gated fakes; production uses observe-git. */
export type RegistryScannerObserve = {
  full(
    workspacePath: string,
    listing?: Pick<WorktreeListing, 'locked' | 'prunable'>,
    options?: ObserveWorkspaceGitOptions
  ): Promise<WorkspaceGitObservations | null>;
  refs(
    workspacePath: string,
    previous: WorkspaceGitObservations | null,
    options?: ObserveWorkspaceGitRefsOptions
  ): Promise<WorkspaceGitObservations | null>;
};

export type RegistryScannerDeps = {
  /** The owning runtime's git context: the idle gate and the observe defaults' exec. */
  git: RegistryGitContext;
  observe?: RegistryScannerObserve;
  clock?: Clock;
  logger?: Logger;
};

/** Idle-gate anti-starvation deadline; mirrors the scan scheduler's poll floor. */
const SCAN_IDLE_DEADLINE_MS = 5 * 60_000;

/**
 * The registry's reconciliation with the disk (spec: registry-runtime-carveout): the
 * scan pass bodies, the scan lane, the idle gate, and the untracked-line caches. The
 * filesystem is the source of truth — records follow it, never the other way around.
 * Everything the scanner learns lands through the {@link ScanLanding} port; registry
 * state, verbs, and muting stay on the runtime.
 */
export class RegistryScanner {
  private readonly landing: ScanLanding;
  private readonly git: RegistryGitContext;
  private readonly observe: RegistryScannerObserve;
  private readonly clock: Clock;
  private readonly logger: Logger;
  /**
   * The scan lane: serializes scans among themselves, off the runtime's mutation
   * queue, so a slow repository observation never blocks creation/activation verbs
   * (spec: git concurrency model). Scan results land through short re-validated
   * mutation blocks on the runtime.
   */
  private scanQueue: Promise<unknown> = Promise.resolve();
  /** Per-record untracked line-count caches; evicted when the record vanishes. */
  private readonly untrackedCaches = new Map<string, UntrackedLinesCache>();

  constructor(landing: ScanLanding, deps: RegistryScannerDeps) {
    this.landing = landing;
    this.git = deps.git;
    this.observe = deps.observe ?? {
      full: (workspacePath, listing, options) =>
        observeWorkspaceGit(deps.git, workspacePath, listing, options),
      refs: (workspacePath, previous, options) =>
        observeWorkspaceGitRefs(deps.git, workspacePath, previous, options),
    };
    this.clock = deps.clock ?? systemClock;
    this.logger = deps.logger ?? noopLogger;
  }

  /**
   * Scheduler entry point: executes one coalesced scan request on the scan lane.
   * Idle-gated (spec: git concurrency model): the scan defers while its repository
   * has creation/activation/background work queued or in flight, with the poll floor
   * as the anti-starvation deadline.
   */
  async executeScanRequest(request: ScanRequest): Promise<void> {
    // The idle wait happens before the scan lane is taken: one busy repository must
    // not stall every other repository's scans behind its gate.
    const target = this.landing.get(request.id);
    if (!target) return;
    await this.git.schedule.whenIdle(this.repositoryKeyFor(target), SCAN_IDLE_DEADLINE_MS);
    return this.enqueueScan(async () => {
      const record = this.landing.get(request.id);
      if (!record) return;
      if (request.kind === 'repository') {
        await this.scanRepository(record, this.landing.list());
        return;
      }
      if (request.mode === 'refs') {
        await this.scanRefsOnly(record);
        return;
      }
      await this.scanRecordPass(record);
    });
  }

  /**
   * The refresh verb's targeted path: one record's scan, on the scan lane. Returns
   * false when the record was already gone at the lane slot — existence is judged
   * where the scan runs, exactly like the pre-extraction verb body.
   */
  scanRecord(id: string): Promise<boolean> {
    return this.enqueueScan(async () => {
      const record = this.landing.get(id);
      if (!record) return false;
      await this.scanRecordPass(record);
      return true;
    });
  }

  scanHost(): Promise<void> {
    return this.enqueueScan(() => this.scanHostUnqueued());
  }

  /** Drops one record's untracked cache; the runtime's vanish/delete landings call it. */
  evict(id: string): void {
    this.untrackedCaches.delete(id);
  }

  /**
   * One record's stat-keyed untracked line-count cache. The creation path borrows it
   * for the finalize observation so the first scan after a creation is warm.
   */
  untrackedCacheFor(id: string): UntrackedLinesCache {
    let cache = this.untrackedCaches.get(id);
    if (!cache) {
      cache = createUntrackedLinesCache();
      this.untrackedCaches.set(id, cache);
    }
    return cache;
  }

  /** The idle-gate key: the owning repository's path (a record's own path otherwise). */
  private repositoryKeyFor(record: DurableWorkspaceRecord): string {
    if (record.kind === 'worktree' && record.parentId !== null) {
      const parent = this.landing.get(record.parentId);
      if (parent) return parent.path;
    }
    return record.path;
  }

  private async scanHostUnqueued(): Promise<void> {
    const records = this.landing.list();
    const repositories = records.filter((record) => record.kind === 'repository');
    const reconciledWorktreeIds = new Set<string>();

    for (const repository of repositories) {
      const childIds = await this.scanRepository(repository, records);
      for (const id of childIds) reconciledWorktreeIds.add(id);
    }

    // Records the repository pass did not cover: directories, and worktrees whose
    // parent repository is unknown, missing, or unscannable.
    for (const record of this.landing.list()) {
      if (record.kind === 'repository' || reconciledWorktreeIds.has(record.id)) continue;
      await this.scanStandalone(record);
    }
  }

  private async scanRecordPass(record: DurableWorkspaceRecord): Promise<void> {
    if (record.kind === 'repository') {
      await this.scanRepository(record, this.landing.list());
      return;
    }
    if (record.kind === 'worktree' && record.parentId !== null) {
      const parent = this.landing.get(record.parentId);
      if (parent && (await isDirectory(parent.path))) {
        // Reconcile through the owning repository so relinks and locked/prunable land.
        await this.scanRepository(parent, this.landing.list());
        return;
      }
    }
    await this.scanStandalone(record);
  }

  /**
   * Reconciles one present repository and its worktrees with the disk. Returns the ids
   * of every worktree record it settled (so the host scan skips them).
   */
  private async scanRepository(
    repository: DurableWorkspaceRecord,
    records: DurableWorkspaceRecord[]
  ): Promise<Set<string>> {
    const settled = new Set<string>();
    const now = this.clock.now();

    if (!(await isDirectory(repository.path))) {
      await this.landing.vanished(repository.id, now);
      return settled;
    }

    let listings: WorktreeListing[];
    try {
      listings = await listRepositoryWorktrees(this.git, repository.path);
    } catch (error) {
      // Positive assertion: an unscannable repository degrades its own observations and
      // asserts nothing about its worktrees.
      this.logger.warn?.(
        `workspace registry scan of '${repository.path}' failed: ${String(error)}`
      );
      await this.landing.refreshConfig(repository.id, repository.path);
      await this.landing.observation(repository.id, { observedStatus: 'present', git: null }, now);
      return settled;
    }

    // One remote-URL resolution per repository per reconcile pass (spec: probe budget);
    // worktrees share their repository's config, so the cache is safe across children.
    const remoteUrlCache = createRemoteUrlCache();
    const children = records.filter(
      (record) => record.kind === 'worktree' && record.parentId === repository.id
    );
    const childByPath = new Map(children.map((child) => [child.path, child]));
    const childByAdminName = new Map(
      children.flatMap((child) => (child.gitAdminName ? [[child.gitAdminName, child]] : []))
    );

    for (const listing of listings) {
      if (listing.isMain) continue;
      const canonicalPath = await realpathSafe(listing.path);
      if (!(await isDirectory(canonicalPath))) {
        // Prunable admin debris without a directory: nothing to track.
        continue;
      }

      const byPath = childByPath.get(canonicalPath);
      const byAdmin = listing.adminName ? childByAdminName.get(listing.adminName) : undefined;
      const child = byPath ?? byAdmin;
      if (child) {
        settled.add(child.id);
        const git = await this.observe.full(canonicalPath, listing, {
          untrackedCache: this.untrackedCacheFor(child.id),
          remoteUrlCache,
        });
        await this.landing.refreshConfig(child.id, canonicalPath);
        await this.landing.observation(
          child.id,
          {
            // Moved worktrees relink by admin name: identity survives, path follows.
            path: canonicalPath,
            gitAdminName: listing.adminName ?? child.gitAdminName,
            observedStatus: 'present',
            git,
          },
          now
        );
        continue;
      }

      // Host-discovered worktree of a registered repository: adopt under a host-minted id.
      const adoptedId = crypto.randomUUID();
      const adopted: DurableWorkspaceRecord = {
        id: adoptedId,
        kind: 'worktree',
        path: canonicalPath,
        parentId: repository.id,
        origin: 'adopted',
        gitAdminName: listing.adminName ?? null,
        observedStatus: 'present',
        creation: null,
        lastCreateOutcome: null,
        lifecycle: null,
        lastRemovalAttempt: null,
        git: await this.observe.full(canonicalPath, listing, {
          untrackedCache: this.untrackedCacheFor(adoptedId),
          remoteUrlCache,
        }),
        lastActivatedAt: null,
        createdAt: now,
        updatedAt: now,
        lastObservedAt: now,
      };
      if (await this.landing.adoption(adopted)) settled.add(adopted.id);
    }

    for (const child of children) {
      if (settled.has(child.id)) continue;
      settled.add(child.id);
      if (await isDirectory(child.path)) {
        // On disk but no longer listed by the repository (e.g. pruned admin data):
        // observe it directly rather than asserting it gone.
        const git = await this.observe.full(child.path, undefined, {
          untrackedCache: this.untrackedCacheFor(child.id),
          remoteUrlCache,
        });
        await this.landing.refreshConfig(child.id, child.path);
        await this.landing.observation(
          child.id,
          {
            observedStatus: 'present',
            git,
          },
          now
        );
        continue;
      }
      await this.landing.vanished(child.id, now);
    }

    const repositoryGit = await this.observe.full(repository.path, undefined, {
      untrackedCache: this.untrackedCacheFor(repository.id),
      remoteUrlCache,
    });
    await this.landing.refreshConfig(repository.id, repository.path);
    await this.landing.observation(
      repository.id,
      {
        observedStatus: 'present',
        git: repositoryGit,
      },
      now
    );
    return settled;
  }

  /** The cheap scan path: ref-only change — no status, no untracked counting. */
  private async scanRefsOnly(record: DurableWorkspaceRecord): Promise<void> {
    const now = this.clock.now();
    if (record.kind === 'directory') return;
    if (!(await isDirectory(record.path))) {
      await this.landing.vanished(record.id, now);
      return;
    }
    const git = await this.observe.refs(record.path, record.git);
    await this.landing.refreshConfig(record.id, record.path);
    await this.landing.observation(record.id, { observedStatus: 'present', git }, now);
  }

  /** Presence + observations for a record outside any repository reconciliation. */
  private async scanStandalone(record: DurableWorkspaceRecord): Promise<void> {
    const now = this.clock.now();
    if (!(await isDirectory(record.path))) {
      await this.landing.vanished(record.id, now);
      return;
    }
    const git =
      record.kind === 'directory'
        ? null
        : await this.observe.full(record.path, undefined, {
            untrackedCache: this.untrackedCacheFor(record.id),
          });
    await this.landing.refreshConfig(record.id, record.path);
    await this.landing.observation(record.id, { observedStatus: 'present', git }, now);
  }

  /** The scan lane's serializer; see the `scanQueue` field for the design intent. */
  private enqueueScan<T>(operation: () => Promise<T>): Promise<T> {
    const next = this.scanQueue.then(operation, operation);
    this.scanQueue = next.catch(() => undefined);
    return next;
  }
}

async function isDirectory(path: string): Promise<boolean> {
  try {
    return (await fs.stat(path)).isDirectory();
  } catch {
    return false;
  }
}

async function realpathSafe(target: string): Promise<string> {
  try {
    return await fs.realpath(target);
  } catch {
    return target;
  }
}
