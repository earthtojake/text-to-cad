import { execFileSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { TempStoreHandle } from '#primitives/sqlite-store/api';
import {
  workspaceRegistryStore,
  type WorkspaceRegistryDb,
} from '#runtimes/workspace-registry/node/persistence/store';
import { WorkspaceRegistryRuntime } from '#runtimes/workspace-registry/node/runtime';
import { RegistryScanner } from '#runtimes/workspace-registry/node/scan/scanner';
import type { ScanRequest } from '#runtimes/workspace-registry/node/scan/scheduler';

// Self-inflicted scan suppression (spec: workspace-lifecycle-v2, scan minimization):
// background steps hold the scheduler's mute for exactly the id they write into and
// request their own deliberate scans on settle. Asserted at the runtime's injection
// seams — a fake muter records hold ordering, a recording proxy around the real
// scanner (the `createScanner` seam) records the trailing scans — never against
// internal queue state.

function git(cwd: string, ...args: string[]): string {
  return execFileSync('git', args, {
    cwd,
    encoding: 'utf8',
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: 'Test',
      GIT_AUTHOR_EMAIL: 'test@example.com',
      GIT_COMMITTER_NAME: 'Test',
      GIT_COMMITTER_EMAIL: 'test@example.com',
      GIT_TERMINAL_PROMPT: '0',
    },
  }).trim();
}

async function eventually(assertion: () => void, timeoutMs = 10_000): Promise<void> {
  const started = Date.now();
  for (;;) {
    try {
      assertion();
      return;
    } catch (error) {
      if (Date.now() - started > timeoutMs) throw error;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }
}

describe('background steps suppress their own scans', () => {
  let root: string;
  let handle: TempStoreHandle<WorkspaceRegistryDb>;
  let runtime: WorkspaceRegistryRuntime;
  let muteEvents: Array<{ action: 'mute' | 'release'; id: string }>;
  let settleScans: ScanRequest[];

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-suppress-')));
    handle = await workspaceRegistryStore.openTemp();
    muteEvents = [];
    settleScans = [];
    runtime = new WorkspaceRegistryRuntime({
      handle,
      // Settle scans are the only scanner requests the runtime makes itself here (no
      // scheduler is wired): a recording proxy around the real scanner captures them.
      createScanner: (landing, deps) => {
        const scanner = new RegistryScanner(landing, deps);
        return new Proxy(scanner, {
          get(target, property, receiver) {
            if (property === 'executeScanRequest') {
              return (request: ScanRequest) => {
                settleScans.push(request);
                return target.executeScanRequest(request);
              };
            }
            const value = Reflect.get(target, property, receiver);
            return typeof value === 'function' ? value.bind(target) : value;
          },
        });
      },
    });
    runtime.setScanMuter((id) => {
      muteEvents.push({ action: 'mute', id });
      return () => muteEvents.push({ action: 'release', id });
    });
  });

  afterEach(async () => {
    runtime.dispose();
    handle.close();
    await fs.rm(root, { recursive: true, force: true });
  });

  it('copy mutes the worktree, push and fetch mute the repository; each settles deliberately', async () => {
    const repoPath = path.join(root, 'repo');
    await fs.mkdir(repoPath, { recursive: true });
    git(repoPath, 'init', '--initial-branch=main');
    await fs.writeFile(path.join(repoPath, '.gitignore'), '.env\n');
    await fs.writeFile(path.join(repoPath, '.env'), 'SECRET=1\n');
    await fs.writeFile(
      path.join(repoPath, '.emdash.json'),
      JSON.stringify({ preservePatterns: ['.env'] })
    );
    git(repoPath, 'add', '.gitignore', '.emdash.json');
    git(repoPath, 'commit', '-m', 'initial');
    const originPath = path.join(root, 'origin.git');
    git(root, 'init', '--bare', originPath);
    git(repoPath, 'remote', 'add', 'origin', originPath);
    git(repoPath, 'push', '-u', 'origin', 'main');

    const registered = await runtime.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });
    expect(registered.success).toBe(true);

    const created = await runtime.createWorktree({
      workspaceId: 'ws-new',
      repositoryId: 'ws-repo',
      branch: 'feature/suppress',
      baseRef: 'main',
      path: path.join(root, 'suppress-wt'),
      // Legacy wire field: resolved project config is the source of truth.
      preservePatterns: [],
      publish: { remote: 'origin' },
    });
    expect(created.success).toBe(true);

    // All three background steps run: copy (worktree id), push + fetch (repository id).
    await eventually(() => {
      expect(muteEvents.filter((event) => event.action === 'release')).toHaveLength(
        muteEvents.filter((event) => event.action === 'mute').length
      );
      expect(muteEvents.filter((event) => event.id === 'ws-new')).toEqual([
        { action: 'mute', id: 'ws-new' },
        { action: 'release', id: 'ws-new' },
      ]);
      // Push and fetch each hold the repository's mute once.
      expect(
        muteEvents.filter((event) => event.id === 'ws-repo' && event.action === 'mute')
      ).toHaveLength(2);
    });

    // Each settled write requested its deliberate trailing scan: the copy scans the
    // worktree fully; push and fetch refresh refs on the records they touched.
    await eventually(() => {
      expect(settleScans).toContainEqual({ kind: 'workspace', id: 'ws-new', mode: 'full' });
      expect(settleScans).toContainEqual({ kind: 'workspace', id: 'ws-repo', mode: 'refs' });
      expect(settleScans).toContainEqual({ kind: 'workspace', id: 'ws-new', mode: 'refs' });
    });
  });
});
