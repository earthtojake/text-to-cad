import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import { deferred, type Deferred } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import type { IWatchService, WatchEvent, WatchOptions } from '#services/fs-watch/api';
import {
  DEFAULT_ACTIVE_SCAN_DEBOUNCE_MS,
  DEFAULT_SCAN_DEBOUNCE_MS,
  WorkspaceScanScheduler,
  type ScanRequest,
  type ScanTarget,
} from './scheduler';

// Unit tests at the scheduler's public seam: fs events (via a fake watch service) and
// scan targets go in; coalesced scan requests come out. The scheduler never writes the
// registry — its whole contract is which requests it emits and when.

type FakeWatchAttempt = {
  root: string;
  onEvents: (events: WatchEvent[]) => void;
  onError: ((error: unknown) => void) | undefined;
  ready: Deferred<Result<void, unknown>>;
  released: boolean;
};

class FakeWatchService implements IWatchService {
  readonly roots = new Map<string, FakeWatchAttempt>();
  readonly attempts: FakeWatchAttempt[] = [];

  // Readiness stays pending until a test resolves or rejects it. Event-classification tests
  // inject at the scheduler seam directly; readiness behavior has its own explicit coverage.
  watch(root: string, onEvents: (events: WatchEvent[]) => void, options?: WatchOptions) {
    const ready = deferred<Result<void, unknown>>();
    const attempt: FakeWatchAttempt = {
      root,
      onEvents,
      onError: options?.onError,
      ready,
      released: false,
    };
    const handle = {
      ready: () => ready.promise,
      release: () => {
        attempt.released = true;
        if (this.roots.get(root) === attempt) this.roots.delete(root);
        return Promise.resolve();
      },
    };
    this.roots.set(root, attempt);
    this.attempts.push(attempt);
    void ready.promise.then((attached) => {
      if (!attached.success && !attempt.released) attempt.onError?.(attached.error);
    });
    return handle;
  }

  dispose(): Promise<void> {
    return Promise.resolve();
  }

  emit(root: string, events: WatchEvent[]): void {
    this.roots.get(root)?.onEvents(events);
  }

  rejectReady(root: string, error: unknown): FakeWatchAttempt {
    const attempt = this.roots.get(root);
    if (!attempt) throw new Error(`No active watch for ${root}`);
    attempt.ready.resolve(err(error));
    return attempt;
  }

  resolveReady(root: string): FakeWatchAttempt {
    const attempt = this.roots.get(root);
    if (!attempt) throw new Error(`No active watch for ${root}`);
    attempt.ready.resolve(ok(undefined));
    return attempt;
  }

  watchCount(root: string): number {
    return this.attempts.filter((attempt) => attempt.root === root).length;
  }
}

function repoTarget(id: string, repoPath: string): ScanTarget {
  return {
    id,
    kind: 'repository',
    path: repoPath,
    parentId: null,
    gitAdminName: null,
    observedStatus: 'present',
    lastObservedAt: 0,
  };
}

function worktreeTarget(
  id: string,
  worktreePath: string,
  parentId: string,
  gitAdminName: string | null = null
): ScanTarget {
  return {
    id,
    kind: 'worktree',
    path: worktreePath,
    parentId,
    gitAdminName,
    observedStatus: 'present',
    lastObservedAt: 0,
  };
}

async function eventually(assertion: () => void, timeoutMs = 3_000): Promise<void> {
  const started = Date.now();
  for (;;) {
    try {
      assertion();
      return;
    } catch (error) {
      if (Date.now() - started > timeoutMs) throw error;
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  }
}

type Harness = {
  watcher: FakeWatchService;
  requests: ScanRequest[];
  scheduler: WorkspaceScanScheduler;
};

function createHarness(
  targets: ScanTarget[],
  options: {
    debounceMs?: number;
    activeDebounceMs?: number;
    pollIntervalMs?: number;
    active?: Set<string>;
    block?: () => Promise<void>;
  } = {}
): Harness {
  const watcher = new FakeWatchService();
  const requests: ScanRequest[] = [];
  const scheduler = new WorkspaceScanScheduler({
    watcher,
    execute: async (request) => {
      requests.push(request);
      await options.block?.();
    },
    listTargets: () => targets,
    isActive: (id) => options.active?.has(id) ?? false,
    debounceMs: options.debounceMs ?? 20,
    activeDebounceMs: options.activeDebounceMs ?? 5,
    pollIntervalMs: options.pollIntervalMs ?? 60 * 60_000,
  });
  scheduler.start();
  return { watcher, requests, scheduler };
}

describe('WorkspaceScanScheduler', () => {
  it('rescans a target when its watcher becomes ready', async () => {
    const directory: ScanTarget = {
      id: 'dir-1',
      kind: 'directory',
      path: '/plain',
      parentId: null,
      gitAdminName: null,
      observedStatus: 'present',
      lastObservedAt: 0,
    };
    const { watcher, requests, scheduler } = createHarness([directory], { debounceMs: 1 });
    try {
      expect(requests).toHaveLength(0);
      watcher.resolveReady('/plain');

      await eventually(() => {
        expect(requests).toEqual([{ kind: 'workspace', id: 'dir-1', mode: 'full' }]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('classifies ref-only gitdir events onto the cheap path, index onto the full path', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const wt = worktreeTarget('wt-1', '/worktrees/wt', 'repo-1');
    const { watcher, requests, scheduler } = createHarness([repo, wt]);
    try {
      const gitDir = path.join('/repos/main', '.git');
      watcher.emit(gitDir, [{ kind: 'update', path: path.join(gitDir, 'refs/heads/main') }]);
      await eventually(() => {
        // Refs move ripples divergence to the repo and every worktree — cheap scans only.
        expect(requests).toEqual([
          { kind: 'workspace', id: 'repo-1', mode: 'refs' },
          { kind: 'workspace', id: 'wt-1', mode: 'refs' },
        ]);
      });

      requests.length = 0;
      watcher.emit(gitDir, [{ kind: 'update', path: path.join(gitDir, 'index') }]);
      await eventually(() => {
        expect(requests).toEqual([{ kind: 'workspace', id: 'repo-1', mode: 'full' }]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('ignores FETCH_HEAD and ORIG_HEAD writes (no-change fetch churn triggers nothing)', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const wt = worktreeTarget('wt-1', '/worktrees/wt', 'repo-1');
    const { watcher, requests, scheduler } = createHarness([repo, wt], { debounceMs: 5 });
    try {
      const gitDir = path.join('/repos/main', '.git');
      watcher.emit(gitDir, [
        { kind: 'update', path: path.join(gitDir, 'FETCH_HEAD') },
        { kind: 'update', path: path.join(gitDir, 'ORIG_HEAD') },
      ]);
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(requests).toHaveLength(0);

      // A fetch that actually moved refs still fans out via packed-refs / refs/remotes.
      watcher.emit(gitDir, [
        { kind: 'update', path: path.join(gitDir, 'FETCH_HEAD') },
        { kind: 'update', path: path.join(gitDir, 'packed-refs') },
      ]);
      await eventually(() => {
        expect(requests).toEqual([
          { kind: 'workspace', id: 'repo-1', mode: 'refs' },
          { kind: 'workspace', id: 'wt-1', mode: 'refs' },
        ]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('defaults the active debounce to 1 s and the idle debounce to 2 s', () => {
    expect(DEFAULT_SCAN_DEBOUNCE_MS).toBe(2_000);
    expect(DEFAULT_ACTIVE_SCAN_DEBOUNCE_MS).toBe(1_000);
  });

  it('worktree admin changes trigger repository reconciliation (adoption path)', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const { watcher, requests, scheduler } = createHarness([repo]);
    try {
      const gitDir = path.join('/repos/main', '.git');
      watcher.emit(gitDir, [
        { kind: 'create', path: path.join(gitDir, 'worktrees/new-wt/gitdir') },
      ]);
      await eventually(() => {
        expect(requests).toEqual([{ kind: 'repository', id: 'repo-1' }]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('coalesces rapid triggers into one scan, full subsuming refs', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const { watcher, requests, scheduler } = createHarness([repo], { debounceMs: 30 });
    try {
      const gitDir = path.join('/repos/main', '.git');
      for (let i = 0; i < 10; i += 1) {
        watcher.emit(gitDir, [{ kind: 'update', path: path.join(gitDir, 'refs/heads/main') }]);
        watcher.emit('/repos/main', [{ kind: 'update', path: '/repos/main/file.txt' }]);
      }
      await eventually(() => {
        expect(requests).toEqual([{ kind: 'workspace', id: 'repo-1', mode: 'full' }]);
      });
      // Nothing further arrives once the burst has been absorbed.
      await new Promise((resolve) => setTimeout(resolve, 80));
      expect(requests).toHaveLength(1);
    } finally {
      await scheduler.dispose();
    }
  });

  it('triggers arriving during an in-flight scan re-run after it, once', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const repo = repoTarget('repo-1', '/repos/main');
    const { watcher, requests, scheduler } = createHarness([repo], {
      debounceMs: 5,
      block: () => gate,
    });
    try {
      watcher.emit('/repos/main', [{ kind: 'update', path: '/repos/main/a.txt' }]);
      await eventually(() => expect(requests).toHaveLength(1));
      // Three more bursts while the first scan is still running.
      watcher.emit('/repos/main', [{ kind: 'update', path: '/repos/main/b.txt' }]);
      watcher.emit('/repos/main', [{ kind: 'update', path: '/repos/main/c.txt' }]);
      watcher.emit('/repos/main', [{ kind: 'update', path: '/repos/main/d.txt' }]);
      release();
      await eventually(() => expect(requests).toHaveLength(2));
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(requests).toHaveLength(2);
    } finally {
      await scheduler.dispose();
    }
  });

  it('polling floor rescans stale records even with no fs events', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const dir: ScanTarget = {
      id: 'dir-1',
      kind: 'directory',
      path: '/plain',
      parentId: null,
      gitAdminName: null,
      observedStatus: 'missing',
      lastObservedAt: 0,
    };
    const { requests, scheduler } = createHarness([repo, dir], {
      debounceMs: 1,
      pollIntervalMs: 25,
    });
    try {
      await eventually(() => {
        expect(requests).toContainEqual({ kind: 'repository', id: 'repo-1' });
        // Missing records poll too — that is how a returned path is noticed.
        expect(requests).toContainEqual({ kind: 'workspace', id: 'dir-1', mode: 'full' });
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('drops a failed watch and retries it from the polling floor without an unhandled rejection', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const unhandled = vi.fn();
    process.on('unhandledRejection', unhandled);
    const { watcher, scheduler } = createHarness([repo], { pollIntervalMs: 25 });

    try {
      expect(watcher.watchCount('/repos/main')).toBe(1);
      const failed = watcher.rejectReady('/repos/main', new Error('watch attach failed'));

      await eventually(() => {
        expect(failed.released).toBe(true);
        expect(watcher.roots.has('/repos/main')).toBe(false);
      });
      await eventually(() => expect(watcher.watchCount('/repos/main')).toBe(2));
      await new Promise((resolve) => setImmediate(resolve));

      expect(watcher.roots.has('/repos/main')).toBe(true);
      expect(unhandled).not.toHaveBeenCalled();
    } finally {
      process.off('unhandledRejection', unhandled);
      await scheduler.dispose();
    }
  });

  it('a HEAD or reflog event under one worktree admin entry scans only that worktree, refs-only', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const wtA = worktreeTarget('wt-a', '/worktrees/a', 'repo-1', 'a');
    const wtB = worktreeTarget('wt-b', '/worktrees/b', 'repo-1', 'b');
    const { watcher, requests, scheduler } = createHarness([repo, wtA, wtB]);
    try {
      const gitDir = path.join('/repos/main', '.git');
      watcher.emit(gitDir, [
        { kind: 'update', path: path.join(gitDir, 'worktrees/a/HEAD') },
        { kind: 'update', path: path.join(gitDir, 'worktrees/a/logs/HEAD') },
      ]);
      await eventually(() => {
        // Localized to the one worktree that moved — no repository reconcile, no fanout.
        expect(requests).toEqual([{ kind: 'workspace', id: 'wt-a', mode: 'refs' }]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('an index event under a worktree admin entry triggers nothing', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const wtA = worktreeTarget('wt-a', '/worktrees/a', 'repo-1', 'a');
    const { watcher, requests, scheduler } = createHarness([repo, wtA], { debounceMs: 5 });
    try {
      const gitDir = path.join('/repos/main', '.git');
      watcher.emit(gitDir, [{ kind: 'update', path: path.join(gitDir, 'worktrees/a/index') }]);
      await new Promise((resolve) => setTimeout(resolve, 50));
      // Staged-only staleness is corrected by the poll floor; the working-tree
      // watch covers real file changes.
      expect(requests).toHaveLength(0);
    } finally {
      await scheduler.dispose();
    }
  });

  it('membership changes (admin entry or gitdir appearing/disappearing) still reconcile the repo', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const wtA = worktreeTarget('wt-a', '/worktrees/a', 'repo-1', 'a');
    const { watcher, requests, scheduler } = createHarness([repo, wtA]);
    try {
      const gitDir = path.join('/repos/main', '.git');
      watcher.emit(gitDir, [{ kind: 'delete', path: path.join(gitDir, 'worktrees/a') }]);
      await eventually(() => {
        expect(requests).toEqual([{ kind: 'repository', id: 'repo-1' }]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('a HEAD event for an unknown admin entry falls back to repository reconcile', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const { watcher, requests, scheduler } = createHarness([repo]);
    try {
      const gitDir = path.join('/repos/main', '.git');
      // No registered target carries this admin name — membership knowledge is stale.
      watcher.emit(gitDir, [{ kind: 'update', path: path.join(gitDir, 'worktrees/ghost/HEAD') }]);
      await eventually(() => {
        expect(requests).toEqual([{ kind: 'repository', id: 'repo-1' }]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('muted ids drop watcher-driven requests until released; the repo mute silences its fanout', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const wt = worktreeTarget('wt-1', '/worktrees/wt', 'repo-1', 'wt');
    const { watcher, requests, scheduler } = createHarness([repo, wt], { debounceMs: 5 });
    try {
      const gitDir = path.join('/repos/main', '.git');

      // Muting the worktree drops its working-tree events (the artifact copy case).
      const releaseWorktree = scheduler.mute('wt-1');
      watcher.emit('/worktrees/wt', [{ kind: 'create', path: '/worktrees/wt/node_modules/x' }]);
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(requests).toHaveLength(0);

      // Muting the repository silences gitdir classification wholesale, fanout included
      // (the background fetch/push case).
      const releaseRepo = scheduler.mute('repo-1');
      watcher.emit(gitDir, [{ kind: 'update', path: path.join(gitDir, 'packed-refs') }]);
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(requests).toHaveLength(0);

      releaseWorktree();
      releaseRepo();
      watcher.emit(gitDir, [{ kind: 'update', path: path.join(gitDir, 'packed-refs') }]);
      await eventually(() => {
        expect(requests).toEqual([
          { kind: 'workspace', id: 'repo-1', mode: 'refs' },
          { kind: 'workspace', id: 'wt-1', mode: 'refs' },
        ]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('mute is refcounted: overlapping holds only release when the last one does', async () => {
    const repo = repoTarget('repo-1', '/repos/main');
    const { watcher, requests, scheduler } = createHarness([repo], { debounceMs: 5 });
    try {
      const first = scheduler.mute('repo-1');
      const second = scheduler.mute('repo-1');
      first();
      first(); // double release of one hold must not free the other
      watcher.emit('/repos/main', [{ kind: 'update', path: '/repos/main/a.txt' }]);
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(requests).toHaveLength(0);

      second();
      watcher.emit('/repos/main', [{ kind: 'update', path: '/repos/main/a.txt' }]);
      await eventually(() => {
        expect(requests).toEqual([{ kind: 'workspace', id: 'repo-1', mode: 'full' }]);
      });
    } finally {
      await scheduler.dispose();
    }
  });

  it('does not watch missing paths, and drops watches when targets vanish', async () => {
    const targets: ScanTarget[] = [repoTarget('repo-1', '/repos/main')];
    const { watcher, scheduler } = createHarness(targets);
    try {
      expect([...watcher.roots.keys()].sort()).toEqual([
        '/repos/main',
        path.join('/repos/main', '.git'),
      ]);
      targets.length = 0;
      scheduler.syncWatches();
      expect(watcher.roots.size).toBe(0);
    } finally {
      await scheduler.dispose();
    }
  });
});
