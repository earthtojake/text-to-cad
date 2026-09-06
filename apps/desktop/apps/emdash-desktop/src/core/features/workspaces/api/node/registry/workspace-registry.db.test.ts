import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { sshConnections } from '@core/services/app-db/node/schema';
import {
  createWorkspaceRegistry,
  isAnnotatedWorkspace,
  workspaceRegistryTable,
} from './workspace-registry';

const LOCAL_HOST = { location: 'local', sshConnectionId: null } as const;

function hostRecord(id: string, path: string, kind: WorkspaceRecord['kind'] = 'repository') {
  return {
    id,
    kind,
    path,
    parentId: null,
    origin: 'registered' as const,
    gitAdminName: null,
    observedStatus: 'present' as const,
    creation: null,
    lastCreateOutcome: null,
    lifecycle: null,
    lastRemovalAttempt: null,
    git: null,
    lastActivatedAt: null,
    createdAt: 1,
    updatedAt: 1,
    lastObservedAt: 1,
    config: null,
    runtime: null,
  } satisfies WorkspaceRecord;
}

describe('WorkspaceRegistry', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  it('registers managed rows and adopts rows without provenance', async () => {
    const registry = createWorkspaceRegistry(fixture.db, {
      now: () => '2026-01-01T00:00:00.000Z',
    });

    registry.recordCreationIntent({
      id: 'managed',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/repo/managed',
      config: { version: '2', git: { kind: 'none' }, workspace: { kind: 'new-worktree' } },
    });
    registry.adopt({
      id: 'adopted',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/repo/adopted',
    });

    expect(registry.getLive('managed')?.config).not.toBeNull();
    expect(registry.getLive('adopted')?.config).toBeNull();
  });

  it('refreshes only host observations', async () => {
    const registry = createWorkspaceRegistry(fixture.db, {
      now: () => '2026-01-02T00:00:00.000Z',
    });
    registry.adopt({
      id: 'workspace',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/old',
    });

    registry.refresh('workspace', {
      path: '/new',
      observedStatus: 'present',
      observedGit: {
        version: '2',
        branch: 'main',
        dirty: true,
        diffStats: null,
        ahead: null,
        behind: null,
        locked: false,
        prunable: false,
        headOid: null,
        upstream: null,
        prBreadcrumb: null,
      },
      observedAt: Date.parse('2026-01-01T00:00:00.000Z'),
    });

    expect(registry.getLive('workspace')).toMatchObject({
      path: '/new',
      observedStatus: 'present',
      observedGit: { version: '2', branch: 'main', dirty: true },
      observedAt: Date.parse('2026-01-01T00:00:00.000Z'),
      updatedAt: '2026-01-02T00:00:00.000Z',
    });
  });

  it('claims a Host record and explicitly retracks the same canonical id', () => {
    const registry = createWorkspaceRegistry(fixture.db);
    const config = {
      version: '2' as const,
      git: { kind: 'none' as const },
      workspace: { kind: 'new-worktree' as const },
    };
    const first = registry.claim({
      host: LOCAL_HOST,
      record: hostRecord('canonical', '/repo'),
      config,
    });
    expect(first).toMatchObject({ success: true, data: { id: 'canonical', config } });

    registry.untrack(['canonical'], '2026-01-01T00:00:00.000Z');
    expect(registry.getLive('canonical')).toBeUndefined();
    const retracked = registry.claim({
      host: LOCAL_HOST,
      record: hostRecord('canonical', '/repo'),
    });
    expect(retracked).toMatchObject({
      success: true,
      data: { id: 'canonical', untrackedAt: null, config },
    });
  });

  it('refuses Claim resurrection through a pending Tombstone', () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'doomed',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
    });
    registry.tombstone('doomed', {
      version: '1',
      targetRecordId: 'doomed',
      tombstonedAt: 1,
      options: { deleteBranch: false, deleteConversations: false },
    });

    expect(registry.claim({ host: LOCAL_HOST, record: hostRecord('doomed', '/repo') })).toEqual({
      success: false,
      error: { type: 'workspace-tombstoned', workspaceId: 'doomed' },
    });
  });

  it('refuses a competing live id at the canonical Host path', () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'legacy',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
    });

    expect(registry.claim({ host: LOCAL_HOST, record: hostRecord('canonical', '/repo') })).toEqual({
      success: false,
      error: {
        type: 'workspace-identity-conflict',
        path: '/repo',
        incomingId: 'canonical',
        conflictingId: 'legacy',
      },
    });
  });

  it('accepts Host canonicalization of a path spelling for the same id', () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'legacy',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo/../repo',
    });

    const claimed = registry.claim({ host: LOCAL_HOST, record: hostRecord('legacy', '/repo') });
    expect(claimed).toMatchObject({ success: true, data: { path: '/repo' } });
  });

  it('explicitly retracks a Host-confirmed id without teaching Claim to change Hosts', () => {
    const registry = createWorkspaceRegistry(fixture.db);
    fixture.db
      .insert(sshConnections)
      .values([
        { id: 'ssh-old', name: 'Old', host: 'old.example', username: 'user' },
        { id: 'ssh-new', name: 'New', host: 'new.example', username: 'user' },
      ])
      .run();
    registry.recordCreationIntent({
      id: 'workspace',
      type: 'project-ssh',
      kind: 'repository',
      location: 'remote',
      sshConnectionId: 'ssh-old',
      path: '/repo/../repo',
    });
    const record = hostRecord('workspace', '/repo');
    const destination = { location: 'remote' as const, sshConnectionId: 'ssh-new' };

    expect(registry.claim({ host: destination, record })).toMatchObject({
      success: false,
      error: { type: 'workspace-identity-conflict' },
    });
    expect(
      registry.retrack(
        { host: destination, record },
        { location: 'remote', sshConnectionId: 'ssh-old' }
      )
    ).toMatchObject({
      success: true,
      data: { id: 'workspace', path: '/repo', sshConnectionId: 'ssh-new' },
    });
  });

  it('untracks atomically through an optional transaction', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.adopt({
      id: 'workspace',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/repo/worktree',
    });

    const changed = fixture.db.transaction((tx) =>
      registry.untrack(
        ['workspace'],
        '2026-01-01T00:00:00.000Z',
        { observedStatus: 'missing', observedAt: Date.parse('2026-01-01T00:00:00.000Z') },
        tx
      )
    );
    expect(changed).toBe(1);
    expect(registry.getLive('workspace')).toBeUndefined();
  });

  it('purges only rows that are already untracked', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.adopt({
      id: 'workspace',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/repo/worktree',
    });

    expect(() => registry.purge(['workspace'])).toThrow('must be untracked');
    registry.untrack(['workspace'], '2026-01-01T00:00:00.000Z');
    expect(registry.purge(['workspace'])).toBe(1);
    expect(
      fixture.db
        .select()
        .from(workspaceRegistryTable)
        .all()
        .map((row) => row.id)
    ).not.toContain('workspace');
  });

  it('defines annotations as provenance or desktop links', () => {
    expect(isAnnotatedWorkspace({ config: { version: '2' }, hasTaskLink: false })).toBe(true);
    expect(isAnnotatedWorkspace({ config: null, hasTaskLink: true })).toBe(true);
    expect(isAnnotatedWorkspace({ config: null, isProjectRepository: true })).toBe(true);
    expect(isAnnotatedWorkspace({ config: null })).toBe(false);
  });
});
