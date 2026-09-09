import { execFile } from 'node:child_process';
import { mkdir, mkdtemp, readFile, realpath, rm, stat, unlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import {
  encodeResourceUri,
  hostFileRef,
  parseAbsolute,
  type ResourceUri,
} from '@emdash/core/primitives/path/api';
import { filesContract } from '@emdash/core/runtimes/files/api';
import { createFilesController, FilesRuntime } from '@emdash/core/runtimes/files/node';
import { gitContract } from '@emdash/core/runtimes/git/api';
import { createGitController, GitRuntime } from '@emdash/core/runtimes/git/node';
import type { IWatchService, WatchEvent, WatchOptions } from '@emdash/core/services/fs-watch/api';
import { ok } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { client, connect, encodeTopic, memoryTransportPair, serve } from '@emdash/wire/rpc';
import type { Controller } from '@emdash/wire/rpc';
import { afterEach, describe, expect, it } from 'vitest';
import { filesWireContract } from '@core/features/files/api';
import { createFilesWireController } from '@core/features/files/node/wire-controller';

const execFileAsync = promisify(execFile);

const cleanups: Array<() => Promise<void>> = [];

afterEach(async () => {
  await Promise.all(cleanups.splice(0).map((cleanup) => cleanup()));
});

// Lives at the gateway layer because hosting a real files runtime requires the
// runtime's node surface, which feature slices must not import; the gateway is
// where the desktop wires slice controllers to hosted runtimes in production.
describe('files wire controller against a live files runtime', () => {
  it('serves live disk content with watch updates and etag-preconditioned writes', async () => {
    const { dir, watcher, controller } = await makeStack();
    const filePath = path.join(dir, 'draft.md');
    await writeFile(filePath, 'first\n');
    const key = { uri: localUri(filePath), source: 'disk' as const };
    const topic = encodeTopic(filesWireContract.content.states.content.id, key);

    const lease = controller.acquireLive(topic);
    const source = await lease?.ready();
    if (!source) throw new Error('Expected a live content source');
    try {
      const snapshot = await source.snapshot();
      expect(snapshot.data).toMatchObject({ kind: 'text', content: 'first\n' });
      const etag = (snapshot.data as { etag: string }).etag;

      // A disk change surfaces through the per-file parent-directory watch.
      await writeFile(filePath, 'changed on disk\n');
      watcher.emit(dir, [{ kind: 'update', path: filePath }]);
      await waitFor(async () => {
        const updated = (await source.snapshot()).data as { kind: string; content?: string };
        return updated.kind === 'text' && updated.content === 'changed on disk\n';
      });

      const fresh = await source.snapshot();
      const freshEtag = (fresh.data as { etag: string }).etag;
      await expect(
        controller.call('content.write', {
          key,
          input: {
            content: 'written over wire\n',
            precondition: { kind: 'etag', etag: freshEtag },
          },
          mutationId: 'mutation-1',
        })
      ).resolves.toMatchObject({ success: true });
      await expect(readFile(filePath, 'utf8')).resolves.toBe('written over wire\n');

      // A stale etag is rejected at the seam.
      await expect(
        controller.call('content.write', {
          key,
          input: { content: 'must not land\n', precondition: { kind: 'etag', etag } },
          mutationId: 'mutation-2',
        })
      ).resolves.toMatchObject({ success: false, error: { type: 'etag-mismatch' } });
      await expect(readFile(filePath, 'utf8')).resolves.toBe('written over wire\n');
    } finally {
      await lease?.release();
    }
  });

  it('reports a missing file through the closed seam-error enum and recovers on create', async () => {
    const { dir, watcher, controller } = await makeStack();
    const filePath = path.join(dir, 'not-yet.txt');
    const key = { uri: localUri(filePath), source: 'disk' as const };
    const topic = encodeTopic(filesWireContract.content.states.content.id, key);

    const lease = controller.acquireLive(topic);
    const source = await lease?.ready();
    if (!source) throw new Error('Expected a live content source');
    try {
      await expect(source.snapshot()).resolves.toMatchObject({
        data: { kind: 'unavailable', code: 'not-found' },
      });

      await writeFile(filePath, 'arrived\n');
      watcher.emit(dir, [{ kind: 'create', path: filePath }]);
      await waitFor(async () => {
        const updated = (await source.snapshot()).data as { kind: string; content?: string };
        return updated.kind === 'text' && updated.content === 'arrived\n';
      });
    } finally {
      await lease?.release();
    }
  });

  it('serves the tree live model keyed by root ResourceUri and exclusions', async () => {
    const { dir, controller } = await makeStack();
    await mkdir(path.join(dir, 'src'));
    await writeFile(path.join(dir, 'src/index.ts'), 'export {};\n');
    await mkdir(path.join(dir, 'node_modules/pkg'), { recursive: true });
    const key = {
      root: localUri(dir),
      sessionId: 'session-1',
      exclusions: ['node_modules'],
    };
    const topic = encodeTopic(filesWireContract.tree.model.states.tree.id, key);

    const lease = controller.acquireLive(topic);
    const source = await lease?.ready();
    if (!source) throw new Error('Expected a live tree source');
    try {
      await expect(
        controller.call('tree.model.expand', { key, input: { path: '' }, mutationId: 'expand-1' })
      ).resolves.toMatchObject({ success: true });
      await waitFor(async () => {
        const snapshot = await source.snapshot();
        const entries = (snapshot.data as { entries: Record<string, unknown> }).entries;
        return 'src' in entries && !('node_modules' in entries);
      });
    } finally {
      await lease?.release();
    }
  });

  it('serves fs one-shots and file mutations keyed by ResourceUri', async () => {
    const { dir, controller } = await makeStack();
    await writeFile(path.join(dir, 'present.txt'), 'here\n');

    await expect(
      controller.call('fs.exists', { uri: localUri(path.join(dir, 'present.txt')) })
    ).resolves.toEqual(ok({ exists: true }));
    await expect(
      controller.call('fs.exists', { uri: localUri(path.join(dir, 'absent.txt')) })
    ).resolves.toEqual(ok({ exists: false }));
    await expect(
      controller.call('fs.readText', { uri: localUri(path.join(dir, 'present.txt')) })
    ).resolves.toMatchObject({ success: true, data: { content: 'here\n' } });

    await expect(
      controller.call('fs.createDirectory', { uri: localUri(path.join(dir, 'docs')) })
    ).resolves.toEqual(ok(undefined));
    await expect(stat(path.join(dir, 'docs'))).resolves.toMatchObject({});

    await expect(
      controller.call('fs.createFile', { uri: localUri(path.join(dir, 'docs', 'note.md')) })
    ).resolves.toEqual(ok(undefined));
    await expect(readFile(path.join(dir, 'docs', 'note.md'), 'utf8')).resolves.toBe('');

    await expect(
      controller.call('fs.rename', {
        from: localUri(path.join(dir, 'docs', 'note.md')),
        to: localUri(path.join(dir, 'docs', 'renamed.md')),
      })
    ).resolves.toEqual(ok(undefined));
    await expect(stat(path.join(dir, 'docs', 'renamed.md'))).resolves.toMatchObject({});

    await expect(
      controller.call('fs.copy', {
        from: localUri(path.join(dir, 'docs', 'renamed.md')),
        to: localUri(path.join(dir, 'docs', 'copied.md')),
      })
    ).resolves.toEqual(ok(undefined));
    await expect(stat(path.join(dir, 'docs', 'copied.md'))).resolves.toMatchObject({});

    await expect(
      controller.call('fs.move', {
        from: localUri(path.join(dir, 'docs', 'copied.md')),
        to: localUri(path.join(dir, 'moved.md')),
      })
    ).resolves.toEqual(ok(undefined));
    await expect(stat(path.join(dir, 'moved.md'))).resolves.toMatchObject({});
    await expect(stat(path.join(dir, 'docs', 'copied.md'))).rejects.toMatchObject({
      code: 'ENOENT',
    });

    await expect(
      controller.call('fs.delete', {
        uri: localUri(path.join(dir, 'docs')),
        recursive: true,
      })
    ).resolves.toEqual(ok(undefined));
    await expect(stat(path.join(dir, 'docs'))).rejects.toMatchObject({ code: 'ENOENT' });
  });
});

// Exercises the git-source arm of the content model against a real git
// runtime: the controller must resolve the containing checkout for the
// decoded absolute path on its own — no checkout root ever enters a key.
describe('files wire controller serving git-ref content', () => {
  it('serves the same file at HEAD, staged, and a specific commit, read-only', async () => {
    const { repo, controller } = await makeGitStack();
    const filePath = path.join(repo, 'docs', 'notes.md');
    await mkdir(path.join(repo, 'docs'));
    await writeFile(filePath, 'first\n');
    await git(repo, 'add', '.');
    await git(repo, 'commit', '-m', 'first');
    const firstCommit = (await git(repo, 'rev-parse', 'HEAD')).trim();
    await writeFile(filePath, 'second\n');
    await git(repo, 'add', '.');
    await git(repo, 'commit', '-m', 'second');
    await writeFile(filePath, 'staged\n');
    await git(repo, 'add', '.');
    await writeFile(filePath, 'working\n');

    await expect(readGitContent(controller, filePath, { kind: 'head' })).resolves.toMatchObject({
      kind: 'text',
      content: 'second\n',
      readonly: true,
      path: 'docs/notes.md',
    });
    await expect(readGitContent(controller, filePath, { kind: 'staged' })).resolves.toMatchObject({
      kind: 'text',
      content: 'staged\n',
      readonly: true,
    });
    await expect(
      readGitContent(controller, filePath, { kind: 'commit', sha: firstCommit })
    ).resolves.toMatchObject({ kind: 'text', content: 'first\n', readonly: true });
    await expect(
      readGitContent(controller, filePath, {
        kind: 'branch',
        branch: { type: 'local', branch: 'main' },
      })
    ).resolves.toMatchObject({ kind: 'text', content: 'second\n', readonly: true });

    // The working tree stays untouched by ref reads.
    await expect(readFile(filePath, 'utf8')).resolves.toBe('working\n');
  });

  it('still serves HEAD content for a file deleted from the working tree', async () => {
    const { repo, controller } = await makeGitStack();
    const filePath = path.join(repo, 'kept.txt');
    await writeFile(filePath, 'kept\n');
    await git(repo, 'add', '.');
    await git(repo, 'commit', '-m', 'keep');
    await unlink(filePath);

    await expect(readGitContent(controller, filePath, { kind: 'head' })).resolves.toMatchObject({
      kind: 'text',
      content: 'kept\n',
      readonly: true,
    });
  });

  it('rejects the etag write mutation for git sources', async () => {
    const { repo, controller } = await makeGitStack();
    const filePath = path.join(repo, 'readonly.txt');
    await writeFile(filePath, 'committed\n');
    await git(repo, 'add', '.');
    await git(repo, 'commit', '-m', 'commit');

    await expect(
      controller.call('content.write', {
        key: { uri: localUri(filePath), source: { ref: { kind: 'head' } } },
        input: { content: 'must not land\n', precondition: { kind: 'overwrite' } },
        mutationId: 'mutation-git-write',
      })
    ).resolves.toMatchObject({ success: false, error: { type: 'permission-denied' } });
    await expect(readFile(filePath, 'utf8')).resolves.toBe('committed\n');
  });

  it('classifies a path outside any checkout as an unavailable content state', async () => {
    const { plainDir, controller } = await makeGitStack();
    const filePath = path.join(plainDir, 'loose.txt');
    await writeFile(filePath, 'loose\n');

    await expect(readGitContent(controller, filePath, { kind: 'head' })).resolves.toMatchObject({
      kind: 'unavailable',
      code: 'unavailable',
    });
  });

  it('classifies a ref that does not contain the path as not-found', async () => {
    const { repo, controller } = await makeGitStack();
    await writeFile(path.join(repo, 'committed.txt'), 'committed\n');
    await git(repo, 'add', '.');
    await git(repo, 'commit', '-m', 'commit');
    const untracked = path.join(repo, 'untracked.txt');
    await writeFile(untracked, 'untracked\n');

    await expect(readGitContent(controller, untracked, { kind: 'head' })).resolves.toMatchObject({
      kind: 'unavailable',
      code: 'not-found',
    });
    await expect(
      readGitContent(controller, path.join(repo, 'committed.txt'), {
        kind: 'branch',
        branch: { type: 'local', branch: 'no-such-branch' },
      })
    ).resolves.toMatchObject({ kind: 'unavailable', code: 'not-found' });
  });

  it('classifies the unstaged ref as unavailable: the working tree is the disk source', async () => {
    const { repo, controller } = await makeGitStack();
    const filePath = path.join(repo, 'tree.txt');
    await writeFile(filePath, 'tree\n');
    await git(repo, 'add', '.');
    await git(repo, 'commit', '-m', 'commit');

    await expect(readGitContent(controller, filePath, { kind: 'unstaged' })).resolves.toMatchObject(
      { kind: 'unavailable', code: 'unavailable' }
    );
  });
});

async function makeStack() {
  const dir = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-files-wire-')));
  const watcher = new ManualWatcher();
  const runtime = new FilesRuntime({ watcher, idleTtlMs: 10_000 });
  const pair = memoryTransportPair();
  const runtimeController = createFilesController(runtime);
  const stop = serve(pair.right, runtimeController);
  const hostClient = { files: client(filesContract, connect(pair.left)) };
  const controller = createFilesWireController({
    runtimes: { client: async () => ok(hostClient as never) },
  });
  cleanups.push(async () => {
    stop();
    await runtimeController.dispose?.();
    await runtime.dispose();
    await rm(dir, { recursive: true, force: true });
  });
  return { dir, watcher, controller };
}

async function makeGitStack() {
  const dir = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-files-wire-git-')));
  const repo = path.join(dir, 'repo');
  const plainDir = path.join(dir, 'plain');
  await mkdir(repo);
  await mkdir(plainDir);
  await git(repo, 'init', '-b', 'main');
  await git(repo, 'config', 'user.email', 'test@example.com');
  await git(repo, 'config', 'user.name', 'Test User');

  const filesRuntime = new FilesRuntime({ watcher: new ManualWatcher(), idleTtlMs: 10_000 });
  const gitRuntime = new GitRuntime({ watcher: new ManualWatcher(), idleTtlMs: 10_000 });
  const filesPair = memoryTransportPair();
  const filesController = createFilesController(filesRuntime);
  const stopFiles = serve(filesPair.right, filesController);
  const gitPair = memoryTransportPair();
  const gitController = createGitController(gitRuntime);
  const stopGit = serve(gitPair.right, gitController);
  const hostClient = {
    files: client(filesContract, connect(filesPair.left)),
    git: client(gitContract, connect(gitPair.left)),
  };
  const controller = createFilesWireController({
    runtimes: { client: async () => ok(hostClient as never) },
  });
  cleanups.push(async () => {
    stopFiles();
    stopGit();
    await filesController.dispose?.();
    await gitController.dispose?.();
    await filesRuntime.dispose();
    await gitRuntime.dispose();
    await rm(dir, { recursive: true, force: true });
  });
  return { repo, plainDir, controller };
}

async function git(cwd: string, ...args: string[]): Promise<string> {
  const { stdout } = await execFileAsync('git', args, { cwd });
  return stdout;
}

async function readGitContent(
  controller: Controller,
  nativePath: string,
  ref: unknown
): Promise<unknown> {
  const key = { uri: localUri(nativePath), source: { ref } };
  const topic = encodeTopic(filesWireContract.content.states.content.id, key);
  const lease = controller.acquireLive(topic);
  const source = await lease?.ready();
  if (!source) throw new Error('Expected a live git content source');
  try {
    return (await source.snapshot()).data;
  } finally {
    await lease?.release();
  }
}

function localUri(nativePath: string): ResourceUri {
  const parsed = parseAbsolute(nativePath, {
    profile: {
      style: path.sep === '\\' ? 'win32' : 'posix',
      unicodeNormalization: 'preserve',
    },
  });
  if (!parsed.success) throw new Error(parsed.error.message);
  return encodeResourceUri(hostFileRef(LOCAL_HOST_REF, parsed.data));
}

class ManualWatcher implements IWatchService {
  private readonly entries = new Map<
    string,
    { onEvents: (events: WatchEvent[]) => void; options: WatchOptions }
  >();

  watch(root: string, onEvents: (events: WatchEvent[]) => void, options: WatchOptions = {}) {
    this.entries.set(root, { onEvents, options });
    return {
      ready: async () => ok(undefined),
      release: async () => {
        this.entries.delete(root);
      },
    };
  }

  emit(root: string, events: WatchEvent[]): void {
    this.entries.get(root)?.onEvents(events);
  }

  async dispose(): Promise<void> {
    this.entries.clear();
  }
}
