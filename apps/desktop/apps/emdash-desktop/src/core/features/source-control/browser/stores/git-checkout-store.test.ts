import type {
  CheckoutHeadState,
  CheckoutStatusState,
  CheckoutUpstream,
} from '@emdash/core/runtimes/git/api';
import { localBranchRefSchema, remoteBranchRefSchema } from '@emdash/core/runtimes/git/api';
import { err, ok } from '@emdash/shared';
import { cell, expose, flushStateTurn } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as SourceControlClientModule from '@core/features/source-control/api/browser/client';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import { sourceControlContract } from '../../api';
import { GitCheckoutStore } from './git-checkout-store';

const mocks = vi.hoisted(() => ({
  getChangedFiles: vi.fn(),
  getGitRepositoryStore: vi.fn(),
  pushRun: vi.fn(),
  readFileText: vi.fn(),
}));

let statusState: ReturnType<typeof cell<CheckoutStatusState>>;
let headState: ReturnType<typeof cell<CheckoutHeadState>>;
let wire: ReturnType<typeof createSourceControlWire> | undefined;
let stageStarted: Deferred<void>;
let releaseStage: Deferred<void>;
let failStage: boolean;
let unstageStarted: Deferred<void>;
let releaseUnstage: Deferred<void>;

vi.mock('@core/features/source-control/api/browser/client', async (importOriginal) => {
  const actual = await importOriginal<typeof SourceControlClientModule>();
  return {
    ...actual,
    getSourceControlClient: async () => wire!.client,
  };
});

vi.mock('@core/features/files/api/browser/client', () => ({
  getFilesClient: async () => ({
    fs: {
      readText: mocks.readFileText,
    },
  }),
}));

vi.mock('@core/features/source-control/api/browser/stores/source-control-selectors', () => ({
  getGitRepositoryStore: mocks.getGitRepositoryStore,
}));

describe('GitCheckoutStore', () => {
  beforeEach(() => {
    statusState = cell(status());
    headState = cell(head('main'));
    stageStarted = deferred<void>();
    releaseStage = deferred<void>();
    failStage = false;
    unstageStarted = deferred<void>();
    releaseUnstage = deferred<void>();
    mocks.getChangedFiles.mockResolvedValue(ok({ files: [] }));
    mocks.getGitRepositoryStore.mockReturnValue({
      pushRemote: { name: 'origin', url: 'https://example.com/repo.git' },
    });
    mocks.pushRun.mockImplementation(async () => {
      headState.set(head('main'));
      return ok({ output: '' });
    });
    wire = createSourceControlWire();
  });

  afterEach(async () => {
    await wire?.dispose();
    wire = undefined;
    vi.clearAllMocks();
  });

  it('binds status and head through remote and refreshes changed files on status updates', async () => {
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();

    await waitFor(() => store.branchName === 'main');

    expect(store.hasData).toBe(true);
    expect(store.branchName).toBe('main');
    expect(store.aheadCount).toBe(2);
    expect(store.behindCount).toBe(1);
    expect(store.isPublished).toBe(true);
    expect(mocks.getChangedFiles).toHaveBeenCalledTimes(2);

    statusState.set(status('src/index.ts'));
    await waitFor(() => store.fileChanges.some((change) => change.path === 'src/index.ts'));

    expect(mocks.getChangedFiles).toHaveBeenCalledTimes(4);
    store.dispose();
  });

  it('uses checkout upstream state instead of repository branch inventory', async () => {
    headState.set(head('main', { kind: 'none' }));
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => store.branchName === 'main');

    expect(store.isPublished).toBe(false);
    expect(store.aheadCount).toBe(0);
    expect(store.behindCount).toBe(0);
    expect(mocks.getGitRepositoryStore).not.toHaveBeenCalled();
    store.dispose();
  });

  it('does not treat a local upstream as a published branch', async () => {
    headState.set(
      head('main', {
        kind: 'local',
        mergeRef: localBranchRefSchema.parse('refs/heads/other'),
        tracking: {
          kind: 'resolved',
          ref: localBranchRefSchema.parse('refs/heads/other'),
          oid: '1234567890123456789012345678901234567890',
          ahead: 3,
          behind: 2,
        },
      })
    );
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => store.branchName === 'main');

    expect(store.isPublished).toBe(false);
    expect(store.aheadCount).toBe(3);
    expect(store.behindCount).toBe(2);
    store.dispose();
  });

  it('publishes through the checkout and refreshes head before settling', async () => {
    headState.set(head('main', { kind: 'none' }));
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => store.branchName === 'main');
    const snapshotSpy = vi.spyOn(headState.__stateNode, 'currentSnapshot');
    snapshotSpy.mockClear();

    await expect(store.publishCurrentBranch()).resolves.toMatchObject({ success: true });
    await waitFor(() => store.isPublished);

    expect(mocks.pushRun).toHaveBeenCalledWith(
      expect.objectContaining({
        workspaceId: 'workspace-1',
        remote: 'origin',
      }),
      expect.anything()
    );
    expect(snapshotSpy).toHaveBeenCalled();
    store.dispose();
  });

  it('refuses publish when the repository has no push remote', async () => {
    mocks.getGitRepositoryStore.mockReturnValue({ pushRemote: null });
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => store.branchName === 'main');

    await expect(store.publishCurrentBranch()).resolves.toEqual(
      err({ type: 'no_remote', message: 'This repository has no git remotes.' })
    );
    expect(mocks.pushRun).not.toHaveBeenCalled();
    store.dispose();
  });

  it('resync refreshes remote status and head state', async () => {
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => store.branchName === 'main');

    headState.set(head('feature'));
    await store.resync();
    await waitFor(() => store.branchName === 'feature');

    expect(store.headDisplay).toBe('feature');
    store.dispose();
  });

  it('projects staged membership before the mutation settles', async () => {
    statusState.set(status('src/index.ts'));
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => hasPath(store.unstagedFileChanges, 'src/index.ts'));

    const staging = store.stageFiles(['src/index.ts']);
    await stageStarted.promise;
    try {
      expect(hasPath(store.unstagedFileChanges, 'src/index.ts')).toBe(false);
      expect(hasPath(store.stagedFileChanges, 'src/index.ts')).toBe(true);
    } finally {
      releaseStage.resolve();
      await staging;
      store.dispose();
    }
  });

  it('keeps staged membership while diff metadata catches up', async () => {
    statusState.set(status('src/index.ts'));
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => hasPath(store.unstagedFileChanges, 'src/index.ts'));
    const changedFiles = deferred<ReturnType<typeof emptyChangesResult>>();
    mocks.getChangedFiles.mockReturnValue(changedFiles.promise);

    const staging = store.stageFiles(['src/index.ts']);
    await stageStarted.promise;
    releaseStage.resolve();
    await staging;

    expect(hasPath(store.unstagedFileChanges, 'src/index.ts')).toBe(false);
    expect(hasPath(store.stagedFileChanges, 'src/index.ts')).toBe(true);

    changedFiles.resolve(emptyChangesResult());
    await waitFor(() => hasPath(store.stagedFileChanges, 'src/index.ts'));
    expect(hasPath(store.unstagedFileChanges, 'src/index.ts')).toBe(false);
    store.dispose();
  });

  it('rolls optimistic staged membership back when the mutation fails', async () => {
    failStage = true;
    statusState.set(status('src/index.ts'));
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => hasPath(store.unstagedFileChanges, 'src/index.ts'));

    const staging = store.stageFiles(['src/index.ts']);
    await stageStarted.promise;
    expect(hasPath(store.unstagedFileChanges, 'src/index.ts')).toBe(false);
    expect(hasPath(store.stagedFileChanges, 'src/index.ts')).toBe(true);

    releaseStage.resolve();
    await expect(staging).resolves.toEqual(err({ type: 'git_error', message: 'stage failed' }));
    await waitFor(() => hasPath(store.unstagedFileChanges, 'src/index.ts'));
    expect(hasPath(store.stagedFileChanges, 'src/index.ts')).toBe(false);
    store.dispose();
  });

  it('projects unstaged membership before the mutation settles', async () => {
    statusState.set(stagedStatus('src/index.ts'));
    const store = new GitCheckoutStore('project-1', 'workspace-1', '/repo');
    store.start();
    await waitFor(() => hasPath(store.stagedFileChanges, 'src/index.ts'));

    const unstaging = store.unstageFiles(['src/index.ts']);
    await unstageStarted.promise;
    try {
      expect(hasPath(store.stagedFileChanges, 'src/index.ts')).toBe(false);
      expect(hasPath(store.unstagedFileChanges, 'src/index.ts')).toBe(true);
    } finally {
      releaseUnstage.resolve();
      await unstaging;
      store.dispose();
    }
  });
});

function createSourceControlWire() {
  const repositoryProvider = expose(sourceControlContract.repository.model, {
    refs: cell({ branches: [], tags: [], remoteHeads: [] }),
    remotes: cell({ remotes: [] }),
  });
  const checkoutProvider = expose(
    sourceControlContract.checkout.model,
    {
      status: statusState,
      head: headState,
    },
    {
      mutations: {
        async stage(context) {
          stageStarted.resolve();
          await releaseStage.promise;
          if (failStage) return err({ type: 'git_error', message: 'stage failed' });
          const path = context.input.paths[0];
          if (!path) return ok<void>();
          const revision = statusState.set(stagedStatus(path), {
            mutationIds: [context.mutationId],
          });
          await context.observed('status', revision);
          return ok<void>();
        },
        async unstage(context) {
          unstageStarted.resolve();
          await releaseUnstage.promise;
          const path = context.input.paths[0];
          if (!path) return ok<void>();
          const revision = statusState.set(status(path), {
            mutationIds: [context.mutationId],
          });
          await context.observed('status', revision);
          return ok<void>();
        },
        async stageAll() {
          return ok<void>();
        },
        async unstageAll() {
          return ok<void>();
        },
        async revert() {
          return ok<void>();
        },
        async revertAll() {
          return ok<void>();
        },
        async commit() {
          return ok({ hash: 'abc123' });
        },
      },
    }
  );

  return createTestWire(sourceControlContract, {
    repository: {
      model: repositoryProvider,
      listWorktrees: vi.fn(),
      getDefaultBranch: vi.fn(),
      fetch: { run: vi.fn() },
      fetchPrForReview: { run: vi.fn() },
    },
    checkout: {
      model: checkoutProvider,
      getChangedFiles: mocks.getChangedFiles,
      getFile: vi.fn(),
      download: vi.fn(),
      getLog: vi.fn(),
      getCommit: vi.fn(),
      getCommitFiles: vi.fn(),
      blame: vi.fn(),
      push: { run: vi.fn() },
      publish: { run: mocks.pushRun },
      pull: { run: vi.fn() },
    },
  } as never);
}

function head(
  name: string,
  upstream: CheckoutUpstream = {
    kind: 'remote',
    remote: 'origin',
    mergeRef: localBranchRefSchema.parse(`refs/heads/${name}`),
    tracking: {
      kind: 'resolved',
      ref: remoteBranchRefSchema.parse(`refs/remotes/origin/${name}`),
      oid: '1234567890123456789012345678901234567890',
      ahead: 2,
      behind: 1,
    },
  }
): CheckoutHeadState {
  return {
    kind: 'branch',
    ref: localBranchRefSchema.parse(`refs/heads/${name}`),
    oid: '1234567890123456789012345678901234567890',
    upstream,
  };
}

function status(changedPath?: string): CheckoutStatusState {
  const entries: Extract<CheckoutStatusState, { kind: 'ok' }>['entries'] = {};
  if (changedPath) {
    const path = changedPath as keyof typeof entries;
    entries[path] = {
      path,
      index: 'unmodified',
      worktree: 'modified',
      isConflicted: false,
    };
  }
  return {
    kind: 'ok',
    entries,
    summary: {
      staged: 0,
      unstaged: changedPath ? 1 : 0,
      conflicted: 0,
      untracked: 0,
    },
    operation: 'none',
  };
}

function stagedStatus(changedPath: string): CheckoutStatusState {
  const path = portablePath(changedPath);
  return {
    kind: 'ok',
    entries: {
      [path]: {
        path,
        index: 'modified',
        worktree: 'unmodified',
        isConflicted: false,
      },
    },
    summary: { staged: 1, unstaged: 0, conflicted: 0, untracked: 0 },
    operation: 'none',
  };
}

function emptyChangesResult() {
  return ok({ files: [] });
}

function hasPath(changes: readonly { path: string }[], path: string): boolean {
  return changes.some((change) => change.path === path);
}

interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let index = 0; index < 50; index += 1) {
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    flushStateTurn();
    if (predicate()) return;
  }
  expect(predicate()).toBe(true);
}
