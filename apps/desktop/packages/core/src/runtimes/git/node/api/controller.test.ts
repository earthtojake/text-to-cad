import { execFile } from 'node:child_process';
import { mkdtemp, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { ok, type Result } from '@emdash/shared';
import { createLiveJobReplicaCache } from '@emdash/wire/live';
import {
  client,
  connect,
  createController,
  defineContract,
  memoryTransportPair,
  serve,
  type LiveUpdate,
} from '@emdash/wire/rpc';
import { describe, expect, it } from 'vitest';
import { gitContract } from '#runtimes/git/api';
import { GitRuntime } from '#runtimes/git/node/git-runtime';
import { gitPath, hostPath } from '#runtimes/git/node/testing/paths';
import type { IWatchService, WatchEvent, WatchOptions } from '#services/fs-watch/api';
import { createGitController } from './controller';
import { createGitProcedures } from './procedures';

const execFileAsync = promisify(execFile);

function unwrap<T, E>(result: Result<T, E>): T {
  if (!result.success) throw result.error;
  return result.data;
}

const checkoutSelector = (root: string) => ({ checkout: hostPath(root) });
const repositorySelector = (root: string) => ({ repository: hostPath(root) });

function makeClient(runtime: GitRuntime) {
  const pair = memoryTransportPair();
  const controller = createGitController(runtime);
  const stop = serve(pair.right, controller);
  const contractClient = client(gitContract, connect(pair.left));
  return {
    client: contractClient,
    dispose: () => {
      stop();
      controller.dispose?.();
    },
  };
}

function createNoopWatcher(onRelease?: () => void): IWatchService {
  return {
    watch: () => ({
      ready: async () => ok(undefined),
      release: async () => {
        onRelease?.();
      },
    }),
    dispose: async () => {},
  };
}

async function makeRepo(): Promise<string> {
  const repo = await mkdtemp(path.join(tmpdir(), 'emdash-git-controller-'));
  await execFileAsync('git', ['init', '-b', 'main'], { cwd: repo });
  await execFileAsync('git', ['config', 'user.email', 'test@example.com'], { cwd: repo });
  await execFileAsync('git', ['config', 'user.name', 'Test User'], { cwd: repo });
  await writeFile(path.join(repo, 'tracked.txt'), 'before\n', 'utf8');
  await execFileAsync('git', ['add', 'tracked.txt'], { cwd: repo });
  await execFileAsync('git', ['commit', '-m', 'initial'], { cwd: repo });
  return await realpath(repo);
}

async function makeRepoWithRemote(): Promise<{ repo: string; remote: string }> {
  const repo = await makeRepo();
  const remote = await mkdtemp(path.join(tmpdir(), 'emdash-git-controller-remote-'));
  await execFileAsync('git', ['init', '--bare'], { cwd: remote });
  await execFileAsync('git', ['remote', 'add', 'origin', remote], { cwd: repo });
  return { repo, remote };
}

async function waitFor(condition: () => boolean, message: string): Promise<void> {
  const deadline = Date.now() + 2_000;
  while (!condition()) {
    if (Date.now() >= deadline) throw new Error(message);
    await new Promise<void>((resolve) => setTimeout(resolve, 10));
  }
}

describe('createGitController', () => {
  it('mounts live models and mutations under a parent wire contract', async () => {
    const repo = await makeRepo();
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const workspaceContract = defineContract({ git: gitContract });
    const procedures = createGitProcedures(runtime, workspaceContract.git);
    const controller = createController(workspaceContract, {
      git: procedures,
    });
    const pair = memoryTransportPair();
    const stop = serve(pair.right, controller);
    const git = client(workspaceContract, connect(pair.left)).git;

    try {
      expect(workspaceContract.git.repository.model.id).toBe('git.repository.model');
      const repository = repositorySelector(repo);
      const refs = await git.repository.model.state(repository, 'refs').snapshot();
      expect(refs.data.branches).toEqual([
        expect.objectContaining({ type: 'local', ref: 'refs/heads/main' }),
      ]);

      const checkout = checkoutSelector(repo);
      await writeFile(path.join(repo, 'tracked.txt'), 'after\n', 'utf8');
      const staged = await git.checkout.model.mutate('stage', {
        key: checkout,
        input: { paths: [gitPath('tracked.txt')] },
      });
      expect(staged.success).toBe(true);
      if (staged.success) {
        expect(staged.data.cursors).toEqual(
          expect.arrayContaining([expect.objectContaining({ model: 'git.checkout.model.status' })])
        );
      }
    } finally {
      stop();
      controller.dispose?.();
      await runtime.dispose();
      await rm(repo, { recursive: true, force: true });
    }
  });

  it('serves live snapshots and streams checkout status updates through a mutation', async () => {
    const repo = await makeRepo();
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);

    try {
      const repository = repositorySelector(repo);
      const refs = await git.repository.model.state(repository, 'refs').snapshot();
      expect(refs.data.branches).toEqual([
        expect.objectContaining({ type: 'local', ref: 'refs/heads/main' }),
      ]);

      const checkout = checkoutSelector(repo);
      await writeFile(path.join(repo, 'tracked.txt'), 'after\n', 'utf8');

      const updates: LiveUpdate[] = [];
      const detach = await git.checkout.model
        .state(checkout, 'status')
        .attach((update) => updates.push(update));

      const stageResult = await git.checkout.model.mutate('stage', {
        key: checkout,
        input: { paths: [gitPath('tracked.txt')] },
      });
      expect(stageResult.success).toBe(true);

      await waitFor(() => updates.length > 0, 'expected a status update after staging');

      const status = await git.checkout.model.state(checkout, 'status').snapshot();
      expect(status.data.kind).toBe('ok');
      if (status.data.kind !== 'ok') throw new Error(`Expected ok status, got ${status.data.kind}`);
      expect(status.data.entries[gitPath('tracked.txt')]).toMatchObject({
        index: 'modified',
        worktree: 'unmodified',
      });

      await detach();
    } finally {
      dispose();
      await runtime.dispose();
      await rm(repo, { recursive: true, force: true });
    }
  });

  it('streams Git-owned file content for the index and mutable refs', async () => {
    const repo = await makeRepo();
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);
    const checkout = checkoutSelector(repo);
    const filePath = gitPath('tracked.txt');
    const headKey = { ...checkout, path: filePath, source: { kind: 'head' as const } };
    const indexKey = { ...checkout, path: filePath, source: { kind: 'index' as const } };

    try {
      await expect(
        git.checkout.content.state(headKey, 'content').snapshot()
      ).resolves.toMatchObject({ data: { kind: 'text', content: 'before\n' } });

      await writeFile(path.join(repo, filePath), 'after\n', 'utf8');
      await expect(
        git.checkout.model.mutate('stage', {
          key: checkout,
          input: { paths: [filePath] },
        })
      ).resolves.toMatchObject({ success: true });
      await expect(
        git.checkout.content.state(indexKey, 'content').snapshot()
      ).resolves.toMatchObject({ data: { kind: 'text', content: 'after\n' } });
      await expect(
        git.checkout.content.state(headKey, 'content').snapshot()
      ).resolves.toMatchObject({ data: { kind: 'text', content: 'before\n' } });

      await expect(
        git.checkout.model.mutate('commit', {
          key: checkout,
          input: { message: 'update content' },
        })
      ).resolves.toMatchObject({ success: true });
      await expect(
        git.checkout.content.state(headKey, 'content').snapshot()
      ).resolves.toMatchObject({ data: { kind: 'text', content: 'after\n' } });
    } finally {
      dispose();
      await runtime.dispose();
      await rm(repo, { recursive: true, force: true });
    }
  });

  it('refreshes live content when an externally updated tag moves', async () => {
    const repo = await makeRepo();
    await execFileAsync('git', ['tag', 'v1'], { cwd: repo });
    const watcher = new ManualWatcher();
    const runtime = new GitRuntime({ watcher });
    const { client: git, dispose } = makeClient(runtime);
    const key = {
      ...checkoutSelector(repo),
      path: gitPath('tracked.txt'),
      source: {
        kind: 'revision' as const,
        revision: { kind: 'tag' as const, name: 'v1' },
      },
    };

    try {
      const state = git.checkout.content.state(key, 'content');
      await expect(state.snapshot()).resolves.toMatchObject({
        data: { kind: 'text', content: 'before\n' },
      });
      const updates: LiveUpdate[] = [];
      const detach = await state.attach((update) => updates.push(update));
      updates.length = 0;

      await writeFile(path.join(repo, 'tracked.txt'), 'after tag\n');
      await execFileAsync('git', ['commit', '-am', 'move tag'], { cwd: repo });
      await execFileAsync('git', ['tag', '-f', 'v1'], { cwd: repo });
      const gitDir = await realpath(path.join(repo, '.git'));
      watcher.emit(gitDir, [{ kind: 'update', path: path.join(gitDir, 'refs/tags/v1') }]);

      await waitFor(() => updates.length > 0, 'expected moved tag content reconciliation');
      await expect(state.snapshot()).resolves.toMatchObject({
        data: { kind: 'text', content: 'after tag\n' },
      });
      await detach();
    } finally {
      dispose();
      await runtime.dispose();
      await rm(repo, { recursive: true, force: true });
    }
  });

  it('reconciles checkout head and repository refs beside commit', async () => {
    const repo = await makeRepo();
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);
    const checkout = checkoutSelector(repo);
    const repository = repositorySelector(repo);

    try {
      const headUpdates: LiveUpdate[] = [];
      const refUpdates: LiveUpdate[] = [];
      const detachHead = await git.checkout.model
        .state(checkout, 'head')
        .attach((update) => headUpdates.push(update));
      const detachRefs = await git.repository.model
        .state(repository, 'refs')
        .attach((update) => refUpdates.push(update));
      const before = await git.checkout.model.state(checkout, 'head').snapshot();

      await writeFile(path.join(repo, 'tracked.txt'), 'committed\n', 'utf8');
      await git.checkout.model.mutate('stage', {
        key: checkout,
        input: { paths: [gitPath('tracked.txt')] },
      });
      const committed = await git.checkout.model.mutate('commit', {
        key: checkout,
        input: { message: 'second' },
      });
      expect(committed).toMatchObject({ success: true });

      await waitFor(() => headUpdates.length > 0, 'expected checkout head reconciliation');
      await waitFor(() => refUpdates.length > 0, 'expected repository refs reconciliation');
      const after = await git.checkout.model.state(checkout, 'head').snapshot();
      expect(after.data).toMatchObject({ kind: 'branch', ref: 'refs/heads/main' });
      expect(after.data).not.toEqual(before.data);

      await detachRefs();
      await detachHead();
    } finally {
      dispose();
      await runtime.dispose();
      await rm(repo, { recursive: true, force: true });
    }
  });

  it('streams binary blobs for head and index over the download blob channel', async () => {
    const repo = await makeRepo();
    const committedBytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0, 1, 2, 255]);
    const stagedBytes = Buffer.from([0x89, 0x50, 0x4e, 0x47, 9, 8, 7]);
    await writeFile(path.join(repo, 'blob.png'), committedBytes);
    await execFileAsync('git', ['add', 'blob.png'], { cwd: repo });
    await execFileAsync('git', ['commit', '-m', 'add binary'], { cwd: repo });
    await writeFile(path.join(repo, 'blob.png'), stagedBytes);
    await execFileAsync('git', ['add', 'blob.png'], { cwd: repo });
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);
    const checkout = checkoutSelector(repo);

    try {
      const atHead = await git.checkout.download({
        ...checkout,
        path: gitPath('blob.png'),
        source: { kind: 'head' },
      });
      expect(atHead.success).toBe(true);
      if (atHead.success) {
        expect(atHead.data.meta).toEqual({
          name: 'blob.png',
          mimeType: 'image/png',
          size: committedBytes.length,
        });
        expect(Buffer.from(await atHead.data.bytes())).toEqual(committedBytes);
      }

      const atIndex = await git.checkout.download({
        ...checkout,
        path: gitPath('blob.png'),
        source: { kind: 'index' },
      });
      expect(atIndex.success).toBe(true);
      if (atIndex.success) {
        expect(atIndex.data.meta).toEqual({
          name: 'blob.png',
          mimeType: 'image/png',
          size: stagedBytes.length,
        });
        expect(Buffer.from(await atIndex.data.bytes())).toEqual(stagedBytes);
      }

      await expect(
        git.checkout.download({
          ...checkout,
          path: gitPath('missing.png'),
          source: { kind: 'head' },
        })
      ).resolves.toEqual({ success: false, error: { type: 'missing' } });
    } finally {
      dispose();
      await runtime.dispose();
      await rm(repo, { recursive: true, force: true });
    }
  });

  it('delegates checkout queries', async () => {
    const repo = await makeRepo();
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);

    try {
      const log = unwrap(
        await git.checkout.getLog({ ...checkoutSelector(repo), options: { limit: 1 } })
      );
      expect(log.commits).toHaveLength(1);
      expect(log.commits[0]?.subject).toBe('initial');
    } finally {
      dispose();
      await runtime.dispose();
      await rm(repo, { recursive: true, force: true });
    }
  });

  it('releases retained repository and checkout sessions when the runtime is disposed', async () => {
    const repo = await makeRepo();
    let releaseCount = 0;
    const runtime = new GitRuntime({
      watcher: createNoopWatcher(() => {
        releaseCount += 1;
      }),
    });
    const { client: git, dispose } = makeClient(runtime);

    try {
      await git.repository.model.state(repositorySelector(repo), 'refs').snapshot();
      await git.checkout.model.state(checkoutSelector(repo), 'status').snapshot();

      await runtime.dispose();

      await waitFor(
        () => releaseCount === 2,
        `Expected runtime dispose to release 2 retained watch handles, got ${releaseCount}`
      );
    } finally {
      dispose();
      await rm(repo, { recursive: true, force: true });
    }
  });

  it('evicts failed acquisitions so a later request retries the same selector', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'emdash-git-controller-non-repo-'));
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);

    try {
      const state = git.checkout.model.state(checkoutSelector(directory), 'head');
      await expect(state.snapshot()).rejects.toBeTruthy();

      await execFileAsync('git', ['init', '-b', 'main'], { cwd: directory });
      await execFileAsync('git', ['config', 'user.email', 'test@example.com'], { cwd: directory });
      await execFileAsync('git', ['config', 'user.name', 'Test User'], { cwd: directory });

      await expect(state.snapshot()).resolves.toMatchObject({
        data: { kind: 'unborn', ref: expect.stringMatching(/^refs\/heads\//) },
      });
    } finally {
      dispose();
      await runtime.dispose();
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('returns selector resolution failures through fallible procedures', async () => {
    const directory = await mkdtemp(path.join(tmpdir(), 'emdash-git-controller-resolution-'));
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);

    try {
      await expect(
        git.checkout.getFile({
          ...checkoutSelector(directory),
          path: gitPath('missing.txt'),
          source: { kind: 'index' },
        })
      ).resolves.toMatchObject({
        success: false,
        error: { type: 'resolution_failed', path: hostPath(directory) },
      });
    } finally {
      dispose();
      await runtime.dispose();
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('publishes the canonical current branch and settles refreshed upstream state', async () => {
    const { repo, remote } = await makeRepoWithRemote();
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);
    const jobs = createLiveJobReplicaCache(gitContract.checkout.publish, git.checkout.publish);

    try {
      await execFileAsync('git', ['tag', 'main'], { cwd: repo });
      const before = await git.checkout.model.state(checkoutSelector(repo), 'head').snapshot();
      expect(before.data).toMatchObject({
        kind: 'branch',
        ref: 'refs/heads/main',
        upstream: { kind: 'none' },
      });

      const lease = await jobs.start({
        ...checkoutSelector(repo),
        remote: 'origin',
      });
      const handle = await lease.ready();

      await expect(handle.result).resolves.toMatchObject({ output: expect.any(String) });
      await expect(
        execFileAsync('git', ['--git-dir', remote, 'rev-parse', 'refs/heads/main'])
      ).resolves.toMatchObject({ stdout: expect.stringMatching(/[a-f0-9]{40}/) });
      await expect(
        git.checkout.model.state(checkoutSelector(repo), 'head').snapshot()
      ).resolves.toMatchObject({
        data: {
          kind: 'branch',
          ref: 'refs/heads/main',
          upstream: {
            kind: 'remote',
            remote: 'origin',
            mergeRef: 'refs/heads/main',
            tracking: { kind: 'resolved', ahead: 0, behind: 0 },
          },
        },
      });

      await lease.release();
    } finally {
      await jobs.dispose();
      dispose();
      await runtime.dispose();
      await rm(repo, { recursive: true, force: true });
      await rm(remote, { recursive: true, force: true });
    }
  });

  it('fails checkout jobs fast when the selector cannot be resolved', async () => {
    const runtime = new GitRuntime({ watcher: createNoopWatcher() });
    const { client: git, dispose } = makeClient(runtime);
    const jobs = createLiveJobReplicaCache(gitContract.checkout.pull, git.checkout.pull);

    try {
      const lease = await jobs.start(checkoutSelector('/repo'));
      const handle = await lease.ready();
      await expect(handle.result).rejects.toBeTruthy();
      await lease.release();
    } finally {
      await jobs.dispose();
      dispose();
      await runtime.dispose();
    }
  });
});

class ManualWatcher implements IWatchService {
  private readonly entries = new Map<string, (events: WatchEvent[]) => void>();

  watch(root: string, onEvents: (events: WatchEvent[]) => void, _options: WatchOptions = {}) {
    this.entries.set(root, onEvents);
    return {
      ready: async () => ok(undefined),
      release: async () => {
        this.entries.delete(root);
      },
    };
  }

  emit(root: string, events: WatchEvent[]): void {
    this.entries.get(root)?.(events);
  }

  async dispose(): Promise<void> {
    this.entries.clear();
  }
}
