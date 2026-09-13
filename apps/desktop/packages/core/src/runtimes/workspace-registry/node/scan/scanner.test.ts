import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createRegistryGitContext } from '../git-context';
import type { DurableWorkspaceRecord } from '../persistence/record-store';
import { RegistryScanner, type ScanLanding } from './scanner';

// The scanner in isolation (spec: registry-runtime-carveout, PR 2): everything it
// learns lands through the ScanLanding port, so a fake landing observes the whole
// behavior — lane serialization, idle gating, cache eviction, and the positive
// assertion that a failed observation lands nothing.

function record(overrides: Partial<DurableWorkspaceRecord> = {}): DurableWorkspaceRecord {
  return {
    id: 'ws-1',
    kind: 'worktree',
    path: '/tmp/nowhere',
    parentId: null,
    origin: 'registered',
    gitAdminName: null,
    observedStatus: 'present',
    creation: null,
    lastCreateOutcome: null,
    lifecycle: null,
    lastRemovalAttempt: null,
    git: null,
    lastActivatedAt: null,
    createdAt: 1_000,
    updatedAt: 1_000,
    lastObservedAt: 1_000,
    ...overrides,
  };
}

type LandingLog = {
  observations: string[];
  vanished: string[];
  refreshed: string[];
  events: string[];
};

function fakeLanding(records: DurableWorkspaceRecord[]): { landing: ScanLanding; log: LandingLog } {
  const byId = new Map(records.map((entry) => [entry.id, entry]));
  const log: LandingLog = { observations: [], vanished: [], refreshed: [], events: [] };
  const landing: ScanLanding = {
    get: (id) => byId.get(id),
    list: () => [...byId.values()],
    observation: async (id) => {
      log.observations.push(id);
      log.events.push(`observation:${id}`);
    },
    vanished: async (id) => {
      log.vanished.push(id);
    },
    adoption: async () => false,
    refreshConfig: async (id) => {
      log.refreshed.push(id);
      log.events.push(`config:${id}`);
    },
  };
  return { landing, log };
}

describe('RegistryScanner', () => {
  let root: string;

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'scanner-')));
  });

  afterEach(async () => {
    await fs.rm(root, { recursive: true, force: true });
  });

  async function standaloneRecord(id: string): Promise<DurableWorkspaceRecord> {
    const workspacePath = path.join(root, id);
    await fs.mkdir(workspacePath, { recursive: true });
    return record({ id, path: workspacePath });
  }

  it('loads config before publishing a present standalone scan observation', async () => {
    const target = await standaloneRecord('ws-configured');
    const { landing, log } = fakeLanding([target]);
    const scanner = new RegistryScanner(landing, {
      git: createRegistryGitContext(),
      observe: { full: async () => null, refs: async () => null },
    });

    await scanner.scanRecord(target.id);

    expect(log.events).toEqual([`config:${target.id}`, `observation:${target.id}`]);
  });

  it('serializes scans on one lane — the second observation starts after the first lands', async () => {
    const first = await standaloneRecord('ws-first');
    const second = await standaloneRecord('ws-second');
    const { landing } = fakeLanding([first, second]);

    const started: string[] = [];
    let releaseFirst = () => {};
    const scanner = new RegistryScanner(landing, {
      git: createRegistryGitContext(),
      observe: {
        full: async (workspacePath) => {
          started.push(workspacePath);
          if (workspacePath === first.path) {
            await new Promise<void>((resolve) => {
              releaseFirst = resolve;
            });
          }
          return null;
        },
        refs: async () => null,
      },
    });

    const firstScan = scanner.scanRecord(first.id);
    const secondScan = scanner.scanRecord(second.id);
    await new Promise((resolve) => setTimeout(resolve, 25));
    // The lane holds the second scan back while the first observation is wedged.
    expect(started).toEqual([first.path]);

    releaseFirst();
    await Promise.all([firstScan, secondScan]);
    expect(started).toEqual([first.path, second.path]);
  });

  it('defers a scheduler request while its repository has work queued or in flight', async () => {
    const target = await standaloneRecord('ws-busy');
    const { landing, log } = fakeLanding([target]);
    const git = createRegistryGitContext();
    const scanner = new RegistryScanner(landing, {
      git,
      observe: { full: async () => null, refs: async () => null },
    });

    let releaseHold = () => {};
    const hold = git.schedule.withRepoHold(target.path, async () => {
      await new Promise<void>((resolve) => {
        releaseHold = resolve;
      });
    });

    const scanning = scanner.executeScanRequest({ kind: 'workspace', id: target.id, mode: 'full' });
    await new Promise((resolve) => setTimeout(resolve, 25));
    // The idle gate holds the scan while the repository's hold is live.
    expect(log.observations).toEqual([]);

    releaseHold();
    await hold;
    await scanning;
    expect(log.observations).toEqual([target.id]);
  });

  it('hands one stable untracked cache per record and drops it on evict', () => {
    const { landing } = fakeLanding([]);
    const scanner = new RegistryScanner(landing, { git: createRegistryGitContext() });

    const cache = scanner.untrackedCacheFor('ws-1');
    expect(scanner.untrackedCacheFor('ws-1')).toBe(cache);
    scanner.evict('ws-1');
    expect(scanner.untrackedCacheFor('ws-1')).not.toBe(cache);
  });

  it('lands nothing when the observation fails — the positive-assertion invariant', async () => {
    const target = await standaloneRecord('ws-fails');
    const { landing, log } = fakeLanding([target]);
    const scanner = new RegistryScanner(landing, {
      git: createRegistryGitContext(),
      observe: {
        full: async () => {
          throw new Error('git exploded');
        },
        refs: async () => null,
      },
    });

    await expect(scanner.scanRecord(target.id)).rejects.toThrow('git exploded');
    expect(log.observations).toEqual([]);
    expect(log.vanished).toEqual([]);
    expect(log.refreshed).toEqual([]);
  });
});
