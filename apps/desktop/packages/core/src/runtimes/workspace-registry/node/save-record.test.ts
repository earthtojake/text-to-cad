import { describe, expect, it } from 'vitest';
import type { DurableWorkspaceRecord } from './persistence/record-store';
import { sameRecordEssence } from './runtime';

// saveRecord's change detection (spec: registry-runtime-carveout, Decision 5): a
// durable record round-trips through JSON in zod parse order while scan results are
// built as literals, so the comparison must be key-order independent — two permuted
// but equal records must read as unchanged (no spurious updatedAt bump), and a real
// change must still bump.

/** A present worktree record with nested blocks, in one deliberate key order. */
function record(): DurableWorkspaceRecord {
  return {
    id: 'wt-1',
    kind: 'worktree',
    path: '/tmp/wt-1',
    parentId: 'ws-repo',
    origin: 'registered',
    gitAdminName: 'wt-1',
    observedStatus: 'present',
    creation: {
      branch: 'feature/x',
      baseRef: 'origin/main',
      requestedPath: '/tmp/wt-1',
      gitSetup: {
        fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/7/head' },
        followRef: true,
      },
    },
    lastCreateOutcome: { status: 'succeeded', at: 1_000 },
    lifecycle: null,
    lastRemovalAttempt: null,
    git: {
      branch: 'feature/x',
      dirty: false,
      diffStats: { added: 3, deleted: 1 },
      ahead: 1,
      behind: 0,
      locked: false,
      prunable: false,
      headOid: 'abc123',
      upstream: { remote: 'origin', mergeRef: 'refs/pull/7/head', remoteUrl: null },
      prBreadcrumb: null,
    },
    lastActivatedAt: null,
    createdAt: 1_000,
    updatedAt: 2_000,
    lastObservedAt: 2_000,
  };
}

/** The same record with every object level's keys permuted (and fresher stamps). */
function permuted(): DurableWorkspaceRecord {
  const base = record();
  return {
    lastObservedAt: 3_000,
    updatedAt: 3_000,
    createdAt: base.createdAt,
    lastActivatedAt: base.lastActivatedAt,
    git: {
      prBreadcrumb: null,
      upstream: { remoteUrl: null, mergeRef: 'refs/pull/7/head', remote: 'origin' },
      headOid: 'abc123',
      prunable: false,
      locked: false,
      behind: 0,
      ahead: 1,
      diffStats: { deleted: 1, added: 3 },
      dirty: false,
      branch: 'feature/x',
    },
    lastRemovalAttempt: null,
    lifecycle: null,
    lastCreateOutcome: { at: 1_000, status: 'succeeded' },
    creation: {
      gitSetup: {
        followRef: true,
        fetchBranch: { sourceRef: 'refs/pull/7/head', remote: 'origin' },
      },
      requestedPath: '/tmp/wt-1',
      baseRef: 'origin/main',
      branch: 'feature/x',
    },
    observedStatus: 'present',
    gitAdminName: 'wt-1',
    origin: 'registered',
    parentId: 'ws-repo',
    path: '/tmp/wt-1',
    kind: 'worktree',
    id: 'wt-1',
  };
}

describe('saveRecord change detection', () => {
  it('reads two key-order-permuted but equal records as unchanged — no updatedAt bump', () => {
    const previous = record();
    const next = permuted();
    // The permutation is real: a naive stringify comparison would report a change.
    expect(JSON.stringify(previous)).not.toBe(JSON.stringify(next));
    expect(sameRecordEssence(previous, next)).toBe(true);
  });

  it('ignores the bookkeeping stamps (updatedAt, lastObservedAt) by design', () => {
    const previous = record();
    const next = { ...record(), updatedAt: 9_000, lastObservedAt: 9_000 };
    expect(sameRecordEssence(previous, next)).toBe(true);
  });

  it('still detects a genuine change — updatedAt bumps', () => {
    const previous = record();
    const moved = permuted();
    moved.git = moved.git === null ? null : { ...moved.git, headOid: 'def456' };
    expect(sameRecordEssence(previous, moved)).toBe(false);

    const vanished: DurableWorkspaceRecord = {
      ...permuted(),
      observedStatus: 'missing',
      git: null,
    };
    expect(sameRecordEssence(previous, vanished)).toBe(false);
  });
});
