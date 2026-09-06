import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { err, ok } from '@emdash/shared';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import { projects, tasks, type WorkspaceInsert } from '@core/services/app-db/node/schema';
import { WorkspaceRegistryBackfillService } from './workspace-registry-backfill';

function hostRecord(
  id: string,
  path: string,
  kind: WorkspaceRecord['kind'] = 'repository',
  parentId: string | null = null,
  observedStatus: WorkspaceRecord['observedStatus'] = 'present'
): WorkspaceRecord {
  return {
    id,
    kind,
    path,
    parentId,
    origin: 'registered',
    gitAdminName: null,
    observedStatus,
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
  };
}

describe('WorkspaceRegistryBackfillService', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;
  let hostByPath: Map<string, WorkspaceRecord>;
  let kindByPath: Map<string, WorkspaceRecord['kind']>;
  let parentByPath: Map<string, string | null>;
  let missingPaths: Set<string>;
  let reachable: boolean;
  let throwNextCreate: boolean;
  let rejectNextCreate: boolean;
  let errors: string[];
  let createWorkspace: ReturnType<typeof vi.fn>;
  let service: WorkspaceRegistryBackfillService;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    hostByPath = new Map();
    kindByPath = new Map();
    parentByPath = new Map();
    missingPaths = new Set();
    reachable = true;
    throwNextCreate = false;
    rejectNextCreate = false;
    errors = [];
    createWorkspace = vi.fn(async (input: { workspaceId: string; path: string }) => {
      if (throwNextCreate) {
        throwNextCreate = false;
        throw new Error('transport dropped');
      }
      if (rejectNextCreate) {
        rejectNextCreate = false;
        return err({
          type: 'immutable-field-mismatch' as const,
          workspaceId: input.workspaceId,
          message: 'id already belongs to another path',
        });
      }
      const canonical = hostByPath.get(input.path);
      if (canonical) return ok(canonical);
      if (missingPaths.has(input.path)) {
        return err({ type: 'path-not-found' as const, path: input.path });
      }
      const record = hostRecord(
        input.workspaceId,
        input.path,
        kindByPath.get(input.path) ?? 'repository',
        parentByPath.get(input.path) ?? null
      );
      hostByPath.set(input.path, record);
      return ok(record);
    });
    const broker = {
      client: async () =>
        reachable
          ? ok({ workspaceRegistry: { createWorkspace } })
          : err({ type: 'host-unavailable', message: 'offline' }),
    } as unknown as RuntimeBroker;
    service = new WorkspaceRegistryBackfillService({
      db: fixture.db,
      runtimes: broker,
      onError: (context) => errors.push(context),
    });
  });

  afterEach(() => {
    fixture.close();
  });

  function seedRow(id: string, overrides: Partial<WorkspaceInsert> = {}): void {
    createWorkspaceRegistry(fixture.db).recordCreationIntent({
      id,
      type: 'local',
      kind: 'worktree',
      location: 'local',
      sshConnectionId: null,
      path: `/work/${id}`,
      config: { version: '2', git: { kind: 'none' }, workspace: { kind: 'new-worktree' } },
      ...overrides,
    });
  }

  function seedProject(projectId: string, repositoryWorkspaceId: string | null = null): void {
    fixture.db
      .insert(projects)
      .values({ id: projectId, name: projectId, repositoryWorkspaceId })
      .run();
  }

  function seedTask(taskId: string, projectId: string, workspaceId: string): void {
    fixture.db
      .insert(tasks)
      .values({ id: taskId, projectId, name: taskId, status: 'running', workspaceId })
      .run();
  }

  async function run(host: HostRef = LOCAL_HOST_REF) {
    return service.backfillHost(host);
  }

  it('translates legacy ids to Host canonical ids and moves every desktop binding', async () => {
    const config = {
      version: '2' as const,
      git: { kind: 'none' as const },
      workspace: { kind: 'new-worktree' as const },
    };
    seedRow('legacy-repo', { kind: 'repository', path: '/repo', config });
    seedRow('child', {
      path: '/work/child',
      parentId: 'legacy-repo',
      config: null,
      origin: 'registered',
    });
    seedProject('project', 'legacy-repo');
    seedTask('task', 'project', 'legacy-repo');
    hostByPath.set('/repo', hostRecord('canonical-repo', '/repo'));
    hostByPath.set('/work/child', hostRecord('child', '/work/child', 'worktree', 'canonical-repo'));

    await expect(run()).resolves.toEqual({ status: 'complete' });

    const registry = createWorkspaceRegistry(fixture.db);
    expect(registry.getLive('legacy-repo')).toBeUndefined();
    expect(registry.getLive('canonical-repo')).toMatchObject({ path: '/repo', config });
    expect(registry.getLive('child')).toMatchObject({ parentId: 'canonical-repo' });
    expect(fixture.db.select().from(projects).get()?.repositoryWorkspaceId).toBe('canonical-repo');
    expect(fixture.db.select().from(tasks).get()?.workspaceId).toBe('canonical-repo');
  });

  it('does not partially move bindings when the canonical desktop row conflicts', async () => {
    seedRow('legacy-repo', { kind: 'repository', path: '/repo' });
    seedRow('canonical-repo', { kind: 'repository', path: '/other' });
    seedProject('project', 'legacy-repo');
    seedProject('other-project', 'canonical-repo');
    hostByPath.set('/repo', hostRecord('canonical-repo', '/repo'));

    await expect(run()).resolves.toMatchObject({ status: 'terminal-failure' });

    const registry = createWorkspaceRegistry(fixture.db);
    expect(registry.getLive('legacy-repo')).toMatchObject({ path: '/repo' });
    expect(registry.getLive('canonical-repo')).toMatchObject({ path: '/other' });
    expect(fixture.db.select().from(projects).get()?.repositoryWorkspaceId).toBe('legacy-repo');
  });

  it('preserves parent closure and registers parents before their worktrees', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.adopt({
      id: 'legacy-parent',
      type: 'local',
      kind: null,
      location: 'local',
      path: '/repo',
    });
    registry.adopt({
      id: 'legacy-child',
      type: 'local',
      kind: null,
      location: 'local',
      parentId: 'legacy-parent',
      path: '/work/child',
    });
    seedProject('project');
    seedTask('task', 'project', 'legacy-child');
    kindByPath.set('/repo', 'repository');
    kindByPath.set('/work/child', 'worktree');
    parentByPath.set('/work/child', 'legacy-parent');

    await expect(run()).resolves.toEqual({ status: 'complete' });

    expect(createWorkspace.mock.calls.slice(0, 2).map(([input]) => input.workspaceId)).toEqual([
      'legacy-parent',
      'legacy-child',
    ]);
    expect(registry.getLive('legacy-parent')).toMatchObject({ kind: 'repository' });
    expect(registry.getLive('legacy-child')).toMatchObject({
      kind: 'worktree',
      parentId: 'legacy-parent',
    });
  });

  it('preserves repository and directory roots but retires reconstructible mirror rows', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.adopt({
      id: 'repository',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
    });
    registry.adopt({
      id: 'directory',
      type: 'local',
      kind: 'directory',
      location: 'local',
      path: '/dir',
    });
    registry.adopt({
      id: 'mirror-worktree',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/work/mirror',
    });
    kindByPath.set('/dir', 'directory');

    await expect(run()).resolves.toEqual({ status: 'complete' });

    expect(createWorkspace.mock.calls.slice(0, 2).map(([input]) => input.workspaceId)).toEqual([
      'directory',
      'repository',
    ]);
    expect(registry.getLive('mirror-worktree')).toBeUndefined();
  });

  it('skips a missing production path without manufacturing Host state', async () => {
    seedRow('missing-repo', { kind: 'repository', path: '/gone/repo' });
    missingPaths.add('/gone/repo');

    await expect(run()).resolves.toEqual({ status: 'complete' });

    expect(hostByPath.has('/gone/repo')).toBe(false);
    expect(createWorkspaceRegistry(fixture.db).getLive('missing-repo')).toBeDefined();
    expect(errors).toEqual(['workspace registry backfill skipped missing (missing-repo)']);

    createWorkspace.mockClear();
    await expect(run()).resolves.toEqual({ status: 'complete' });
    expect(createWorkspace).not.toHaveBeenCalled();
  });

  it('skips a pathless legacy row without blocking the Host attachment', async () => {
    seedRow('pathless', { kind: 'worktree', path: null });

    await expect(run()).resolves.toEqual({ status: 'complete' });

    expect(createWorkspace).not.toHaveBeenCalled();
    expect(createWorkspaceRegistry(fixture.db).getLive('pathless')).toBeDefined();
    expect(errors).toEqual(['workspace registry backfill skipped pathless (pathless)']);
  });

  it('does not write completion on a transport failure and retries the whole obligation', async () => {
    seedRow('repo', { kind: 'repository', path: '/repo' });
    throwNextCreate = true;

    await expect(run()).resolves.toMatchObject({ status: 'retry-needed' });
    expect(errors).toEqual(['workspace registry backfill retry-needed (local:local)']);

    await expect(run()).resolves.toEqual({ status: 'complete' });
    createWorkspace.mockClear();
    await expect(run()).resolves.toEqual({ status: 'complete' });
    expect(createWorkspace).not.toHaveBeenCalled();
  });

  it('gates snapshot attachment on terminal identity failures', async () => {
    seedRow('repo', { kind: 'repository', path: '/repo' });
    rejectNextCreate = true;

    await expect(run()).resolves.toMatchObject({ status: 'terminal-failure' });
    expect(errors).toEqual(['workspace registry backfill terminal-failure (local:local)']);

    await expect(run()).resolves.toEqual({ status: 'complete' });
    expect(createWorkspace).toHaveBeenCalledTimes(3);
  });

  it('ignores the shipped numeric marker and only trusts the versioned completion', async () => {
    seedRow('repo', { kind: 'repository', path: '/repo' });
    fixture.sqlite
      .prepare(`INSERT INTO kv (key, value, updated_at) VALUES (?, ?, ?)`)
      .run('workspace-registry-backfill:local:local', JSON.stringify(1), Date.now());

    await expect(run()).resolves.toEqual({ status: 'complete' });
    expect(createWorkspace).toHaveBeenCalled();

    createWorkspace.mockClear();
    await expect(run()).resolves.toEqual({ status: 'complete' });
    expect(createWorkspace).not.toHaveBeenCalled();
  });

  it('keeps local and remote obligations independent and retries unreachable hosts', async () => {
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, username) VALUES (?, ?, 'example.test', 'user')`
      )
      .run('ssh-1', 'ssh-1');
    seedRow('remote-repo', {
      kind: 'repository',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      path: '/remote/repo',
    });
    reachable = false;

    await expect(run(hostRef('remote', 'ssh-1'))).resolves.toEqual({
      status: 'retry-needed',
      message: 'offline',
    });
    expect(createWorkspace).not.toHaveBeenCalled();

    reachable = true;
    await expect(run()).resolves.toEqual({ status: 'complete' });
    expect(createWorkspace).not.toHaveBeenCalled();
    await expect(run(hostRef('remote', 'ssh-1'))).resolves.toEqual({ status: 'complete' });
    expect(createWorkspace).toHaveBeenCalledWith({
      workspaceId: 'remote-repo',
      path: '/remote/repo',
    });
  });
});
