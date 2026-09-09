import { beforeEach, describe, expect, it, vi } from 'vitest';

const select = vi.fn();

vi.mock('drizzle-orm', () => ({
  and: vi.fn(() => 'and'),
  eq: vi.fn(() => 'eq'),
  inArray: vi.fn(() => 'inArray'),
  isNotNull: vi.fn(() => 'isNotNull'),
  isNull: vi.fn(() => 'isNull'),
  or: vi.fn(() => 'or'),
}));

vi.mock('@core/features/workspaces/api/node/registry', () => ({
  isAnnotatedWorkspace: (row: { config: unknown; hasTaskLink?: boolean }) =>
    row.config !== null || row.hasTaskLink === true,
  liveWorkspaces: () => 'liveWorkspaces',
  workspaceRegistryTable: {
    id: 'workspaces.id',
    type: 'workspaces.type',
    kind: 'workspaces.kind',
    location: 'workspaces.location',
    sshConnectionId: 'workspaces.sshConnectionId',
    parentId: 'workspaces.parentId',
    path: 'workspaces.path',
    config: 'workspaces.config',
    observedStatus: 'workspaces.observedStatus',
    observedGit: 'workspaces.observedGit',
    observedAt: 'workspaces.observedAt',
    deletionTombstone: 'workspaces.deletionTombstone',
    lastCreateOutcome: 'workspaces.lastCreateOutcome',
    scriptOutcomes: 'workspaces.scriptOutcomes',
    runtimeOverlay: 'workspaces.runtimeOverlay',
  },
}));

vi.mock('@core/services/app-db/node/schema', () => ({
  projects: {
    id: 'projects.id',
    repositoryWorkspaceId: 'projects.repositoryWorkspaceId',
    deletedAt: 'projects.deletedAt',
  },
  tasks: {
    id: 'tasks.id',
    name: 'tasks.name',
    status: 'tasks.status',
    archivedAt: 'tasks.archivedAt',
    updatedAt: 'tasks.updatedAt',
    lastInteractedAt: 'tasks.lastInteractedAt',
    workspaceId: 'tasks.workspaceId',
    projectId: 'tasks.projectId',
    deletedAt: 'tasks.deletedAt',
  },
}));

vi.mock('@core/features/workspaces/api/node/workspace-branch', () => ({
  getProvisionedWorkspaceBranch: vi.fn(() => undefined),
}));

const db = { select } as never;
const taskSessions = { getTask: vi.fn(() => undefined) };
const OBSERVED_AT = Date.parse('2026-01-01T00:00:00.000Z');

describe('listProjectWorkspaces', () => {
  beforeEach(() => {
    select.mockReset();
  });

  it('serves rows and git stats from mirror observations without touching the host', async () => {
    const client = vi.fn();
    select
      .mockReturnValueOnce(projectQuery([{ id: 'project-1', path: '/repo' }]))
      .mockReturnValueOnce(taskRows([]))
      .mockReturnValueOnce(
        workspaceRows([
          mirrorRow({
            id: 'project-1-repository-workspace',
            kind: 'repository',
            path: '/repo',
            observedGit: observedGit({ branch: 'main' }),
          }),
          mirrorRow({
            id: 'workspace-1',
            path: '/repo/feature',
            config: { version: '2' },
            observedGit: observedGit({
              branch: 'feature',
              diffStats: { added: 12, deleted: 3 },
              ahead: 2,
              behind: 1,
            }),
          }),
        ])
      );

    const result = await list({ client });

    expect(client).not.toHaveBeenCalled();
    expect(result.rows[0]).toMatchObject({
      kind: 'root',
      path: '/repo',
      branch: 'main',
      pathState: 'measured',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
    });
    expect(result.rows[1]).toMatchObject({
      kind: 'workspace',
      path: '/repo/feature',
      branch: 'feature',
      gitStats: { added: 12, removed: 3, ahead: 2, behind: 1 },
    });
    expect(result.scannedAt).toBe('2026-01-01T00:00:00.000Z');
  });

  it('returns null git stats when the mirror has no observation yet', async () => {
    select
      .mockReturnValueOnce(projectQuery([{ id: 'project-1', path: '/repo' }]))
      .mockReturnValueOnce(taskRows([]))
      .mockReturnValueOnce(
        workspaceRows([
          mirrorRow({
            id: 'project-1-repository-workspace',
            kind: 'repository',
            path: '/repo',
            observedGit: null,
            observedAt: null,
          }),
        ])
      );

    const result = await list({ client: vi.fn() });

    expect(result.rows[0]).toMatchObject({ kind: 'root', gitStats: null });
    expect(result.rows[0]!.lastObservedAt).toBeUndefined();
  });

  it('projects a missing annotated workspace as path-gone', async () => {
    select
      .mockReturnValueOnce(projectQuery([{ id: 'project-1', path: '/repo' }]))
      .mockReturnValueOnce(
        taskRows([
          {
            taskId: 'task-1',
            name: 'Missing task',
            status: 'in_progress',
            archivedAt: null,
            updatedAt: '2026-01-01T00:00:00.000Z',
            lastInteractedAt: null,
            workspaceId: 'workspace-1',
          },
        ])
      )
      .mockReturnValueOnce(
        workspaceRows([
          mirrorRow({ id: 'project-1-repository-workspace', kind: 'repository', path: '/repo' }),
          mirrorRow({
            id: 'workspace-1',
            path: '/repo/missing',
            observedStatus: 'missing',
            observedGit: null,
          }),
        ])
      );

    const result = await list({ client: vi.fn() });

    expect(result.rows.find((row) => row.workspaceId === 'workspace-1')).toMatchObject({
      kind: 'workspace',
      pathState: 'missing',
      pathIssue: { kind: 'path-gone' },
    });
  });

  it('serves tombstoned rows as pending removals with the active terminal stop', async () => {
    select
      .mockReturnValueOnce(projectQuery([{ id: 'project-1', path: '/repo' }]))
      .mockReturnValueOnce(taskRows([]))
      .mockReturnValueOnce(
        workspaceRows([
          mirrorRow({ id: 'project-1-repository-workspace', kind: 'repository', path: '/repo' }),
          mirrorRow({
            id: 'doomed',
            path: '/repo/doomed',
            config: { version: '2' },
            deletionTombstone: {
              version: '1',
              targetRecordId: 'doomed',
              tombstonedAt: OBSERVED_AT,
              options: { deleteBranch: false, deleteConversations: false },
              attemptEpoch: 0,
              terminalStop: {
                epoch: 0,
                stage: 'remove',
                message: 'worktree is locked',
                at: OBSERVED_AT,
              },
            },
          }),
        ])
      );

    const result = await list({ client: vi.fn() });

    expect(result.rows.find((row) => row.workspaceId === 'doomed')).toMatchObject({
      pendingRemoval: true,
      canDelete: false,
      removalStop: { stage: 'remove', message: 'worktree is locked' },
    });
    expect(result.rows.find((row) => row.kind === 'root')).toMatchObject({
      pendingRemoval: false,
      removalStop: undefined,
    });
  });

  it('hides a terminal stop from an older epoch after a durable retry', async () => {
    select
      .mockReturnValueOnce(projectQuery([{ id: 'project-1', path: '/repo' }]))
      .mockReturnValueOnce(taskRows([]))
      .mockReturnValueOnce(
        workspaceRows([
          mirrorRow({ id: 'project-1-repository-workspace', kind: 'repository', path: '/repo' }),
          mirrorRow({
            id: 'retried',
            path: '/repo/retried',
            config: { version: '2' },
            deletionTombstone: {
              version: '1',
              targetRecordId: 'retried',
              tombstonedAt: OBSERVED_AT,
              options: { deleteBranch: false, deleteConversations: false },
              attemptEpoch: 1,
              terminalStop: {
                epoch: 0,
                stage: 'remove',
                message: 'worktree is locked',
                at: OBSERVED_AT,
              },
            },
          }),
        ])
      );

    const result = await list({ client: vi.fn() });

    expect(result.rows.find((row) => row.workspaceId === 'retried')).toMatchObject({
      pendingRemoval: true,
      removalStop: undefined,
    });
  });

  it('passes the runtime overlay (including lifecycle steps) through to rows', async () => {
    const runtimeOverlay = {
      version: '1',
      creation: { stage: 'add-worktree', startedAt: OBSERVED_AT },
      notices: [],
      activation: null,
      lifecycle: [
        {
          id: 'setup',
          status: 'failed',
          startedAt: OBSERVED_AT,
          finishedAt: OBSERVED_AT,
          message: 'pnpm install failed',
          params: {},
        },
      ],
    };
    select
      .mockReturnValueOnce(projectQuery([{ id: 'project-1', path: '/repo' }]))
      .mockReturnValueOnce(taskRows([]))
      .mockReturnValueOnce(
        workspaceRows([
          mirrorRow({ id: 'project-1-repository-workspace', kind: 'repository', path: '/repo' }),
          mirrorRow({
            id: 'workspace-1',
            path: '/repo/feature',
            config: { version: '2' },
            runtimeOverlay,
          }),
        ])
      );

    const result = await list({ client: vi.fn() });

    expect(result.rows.find((row) => row.workspaceId === 'workspace-1')).toMatchObject({
      runtimeOverlay: {
        creation: { stage: 'add-worktree' },
        lifecycle: [expect.objectContaining({ id: 'setup', status: 'failed' })],
      },
    });
  });

  it('projects prunable worktrees from the git observation', async () => {
    select
      .mockReturnValueOnce(projectQuery([{ id: 'project-1', path: '/repo' }]))
      .mockReturnValueOnce(taskRows([]))
      .mockReturnValueOnce(
        workspaceRows([
          mirrorRow({ id: 'project-1-repository-workspace', kind: 'repository', path: '/repo' }),
          mirrorRow({
            id: 'stale',
            path: '/repo/stale',
            observedGit: observedGit({ prunable: true }),
          }),
        ])
      );

    const result = await list({ client: vi.fn() });

    expect(result.rows.find((row) => row.workspaceId === 'stale')).toMatchObject({
      kind: 'candidate',
      pathState: 'missing',
      pathIssue: { kind: 'prunable' },
    });
  });
});

async function list(runtimes: { client: ReturnType<typeof vi.fn> }, projectId = 'project-1') {
  const { listProjectWorkspaces } = await import('./list-project-workspaces');
  return listProjectWorkspaces({ db, taskSessions, runtimes } as never, projectId);
}

function observedGit(overrides: Record<string, unknown>) {
  return {
    version: '2',
    branch: null,
    dirty: false,
    diffStats: null,
    ahead: null,
    behind: null,
    locked: false,
    prunable: false,
    headOid: null,
    upstream: null,
    prBreadcrumb: null,
    ...overrides,
  };
}

function mirrorRow(overrides: Record<string, unknown>) {
  return {
    id: 'workspace',
    type: 'local',
    kind: 'worktree',
    location: 'local',
    sshConnectionId: null,
    path: '/repo/worktree',
    config: null,
    observedStatus: 'present',
    observedGit: null,
    observedAt: OBSERVED_AT,
    deletionTombstone: null,
    lastCreateOutcome: null,
    scriptOutcomes: null,
    runtimeOverlay: null,
    ...overrides,
  };
}

function projectQuery(rows: Array<{ id: string; path: string }>) {
  return {
    from: () => ({
      leftJoin: () => ({
        where: () => ({
          limit: async () =>
            rows.map((row) => ({
              id: row.id,
              repositoryWorkspaceId: `${row.id}-repository-workspace`,
              repositoryWorkspacePath: row.path,
              repositoryWorkspaceLocation: 'local',
              repositoryWorkspaceSshConnectionId: null,
            })),
        }),
      }),
    }),
  };
}

function workspaceRows(rows: unknown[]) {
  return { from: () => ({ where: async () => rows }) };
}

function taskRows(rows: unknown[]) {
  return { from: () => ({ where: async () => rows }) };
}
