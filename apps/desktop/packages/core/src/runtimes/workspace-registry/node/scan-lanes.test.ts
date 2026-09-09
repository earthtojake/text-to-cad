import { execFileSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ManualClock } from '@emdash/shared/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { TempStoreHandle } from '#primitives/sqlite-store/api';
import {
  workspaceRegistryStore,
  type WorkspaceRegistryDb,
} from '#runtimes/workspace-registry/node/persistence/store';
import { WorkspaceRegistryRuntime } from '#runtimes/workspace-registry/node/runtime';
import { RegistryScanner } from '#runtimes/workspace-registry/node/scan/scanner';

// Scan-lane decoupling (spec: workspace-lifecycle-v2, git concurrency model): scans
// serialize on their own lane and land results through re-validated mutation blocks,
// so a slow repository observation never blocks creation verbs, and a record deleted
// mid-observation stays deleted. The scanner's observe dep is a controllable gate
// (the honest seam); ordering is asserted externally.

const observeGate = { block: false, waiters: [] as Array<() => void>, started: [] as string[] };

function releaseObservations(): void {
  observeGate.block = false;
  for (const waiter of observeGate.waiters.splice(0)) waiter();
}

async function gatedObservation(workspacePath: string): Promise<null> {
  observeGate.started.push(workspacePath);
  if (observeGate.block) {
    await new Promise<void>((resolve) => observeGate.waiters.push(resolve));
  }
  return null;
}

async function eventually(assertion: () => void | Promise<void>, timeoutMs = 5_000): Promise<void> {
  const started = Date.now();
  for (;;) {
    try {
      await assertion();
      return;
    } catch (error) {
      if (Date.now() - started > timeoutMs) throw error;
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
  }
}

describe('workspace registry scan lanes', () => {
  let root: string;
  let handle: TempStoreHandle<WorkspaceRegistryDb>;
  let runtime: WorkspaceRegistryRuntime;

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-lanes-')));
    handle = await workspaceRegistryStore.openTemp();
    runtime = new WorkspaceRegistryRuntime({
      handle,
      clock: new ManualClock(10_000),
      createScanner: (landing, deps) =>
        new RegistryScanner(landing, {
          ...deps,
          observe: {
            full: (workspacePath) => gatedObservation(workspacePath),
            refs: (workspacePath) => gatedObservation(workspacePath),
          },
        }),
    });
    observeGate.block = false;
    observeGate.waiters = [];
    observeGate.started = [];
  });

  afterEach(async () => {
    releaseObservations();
    runtime.dispose();
    handle.close();
    await fs.rm(root, { recursive: true, force: true });
  });

  async function makeRepoWorkspace(id: string, name: string): Promise<string> {
    const repoPath = path.join(root, name);
    await fs.mkdir(repoPath, { recursive: true });
    execFileSync('git', ['init', '--initial-branch=main'], { cwd: repoPath });
    const created = await runtime.createWorkspace({ workspaceId: id, path: repoPath });
    expect(created.success).toBe(true);
    return repoPath;
  }

  it('mutation verbs complete while a scan observation is blocked', async () => {
    await makeRepoWorkspace('ws-scanned', 'scanned');

    observeGate.block = true;
    const scanning = runtime.executeScanRequest({
      kind: 'workspace',
      id: 'ws-scanned',
      mode: 'full',
    });
    await eventually(() => {
      expect(observeGate.started.length).toBeGreaterThan(0);
    });

    // The scan is wedged inside its git observation; a creation verb still lands.
    const workspacePath = path.join(root, 'fresh');
    await fs.mkdir(workspacePath, { recursive: true });
    const created = await runtime.createWorkspace({ workspaceId: 'ws-fresh', path: workspacePath });
    expect(created.success).toBe(true);

    releaseObservations();
    await scanning;
  });

  it('a record deleted mid-observation stays deleted — the scan never resurrects it', async () => {
    await makeRepoWorkspace('ws-doomed', 'doomed');

    observeGate.block = true;
    const scanning = runtime.executeScanRequest({
      kind: 'workspace',
      id: 'ws-doomed',
      mode: 'full',
    });
    await eventually(() => {
      expect(observeGate.started.length).toBeGreaterThan(0);
    });

    const deleted = await runtime.deleteWorkspace({ workspaceId: 'ws-doomed' });
    expect(deleted.success).toBe(true);

    releaseObservations();
    await scanning;

    const records = runtime.scanTargets();
    expect(records.find((record) => record.id === 'ws-doomed')).toBeUndefined();
  });
});
