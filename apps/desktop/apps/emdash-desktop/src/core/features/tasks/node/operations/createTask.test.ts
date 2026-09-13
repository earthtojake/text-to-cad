import { hostRef } from '@emdash/core/primitives/host/api';
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { WorkspaceCreations } from '@core/features/workspaces/api/node/registry-verbs';
import type { TaskRow } from '@core/services/app-db/node/schema';
import { createTask as createTaskOperation } from './createTask';

const mocks = vi.hoisted(() => ({
  transaction: vi.fn(),
  getProject: vi.fn(),
  requireAttached: vi.fn(),
  select: vi.fn(),
  hostIsReachable: vi.fn(),
  resolveWorktreeRoot: vi.fn(),
  findWorkspaceTombstoneConflict: vi.fn(),
  resolveProjectWorkspaceTarget: vi.fn(),
  registryRows: [] as unknown[],
}));
vi.mock('@core/features/workspaces/api/node/registry/workspace-tombstones', () => ({
  findWorkspaceTombstoneConflict: mocks.findWorkspaceTombstoneConflict,
}));
vi.mock('@core/features/workspaces/api/node/project-workspace-target', () => ({
  resolveProjectWorkspaceTarget: mocks.resolveProjectWorkspaceTarget,
}));
const hostIsReachable = mocks.hostIsReachable;
const db = { transaction: mocks.transaction, select: mocks.select } as never;
const projects = { requireAttached: mocks.requireAttached };
const placement = { resolveWorktreeRoot: mocks.resolveWorktreeRoot };
const hostConversations = {
  create: vi.fn(async (input: { id: string }) => ({ success: true as const, data: input })),
  delete: vi.fn(async () => ({ success: true as const, data: undefined })),
};
const projectConfig = { preservePatterns: ['.env'] as string[] };
const workspaceRegistry = {
  createWorkspace: vi.fn(async (input: { workspaceId: string; path: string }) => ({
    success: true as const,
    data: { id: input.workspaceId },
  })),
  createWorktree: vi.fn(async (_input: Record<string, unknown>) => ({
    success: true as const,
    data: undefined,
  })),
  getProjectConfig: vi.fn(async () => ({
    success: true as const,
    data: {
      resolved: {
        preservePatterns: { value: projectConfig.preservePatterns, from: 'personal' as const },
      },
    },
  })),
};
const runtimes = {
  client: vi.fn(async () => ({
    success: true as const,
    data: { conversations: hostConversations, workspaceRegistry },
  })),
} as never;
let creations: WorkspaceCreations;

function createTask(
  _db: typeof db,
  _projects: typeof projects,
  _hostIsReachable: typeof hostIsReachable,
  params: Parameters<typeof createTaskOperation>[5]
) {
  return createTaskOperation(db, projects, placement, runtimes, creations, params);
}

/** Awaits the background worktree creation kicked off for the inserted workspace row. */
async function settleCreation(workspaceId: unknown) {
  await (creations.pending(String(workspaceId)) ?? Promise.resolve());
}

function makeTaskRow(values: Partial<TaskRow>): TaskRow {
  return {
    id: values.id ?? 'task-1',
    projectId: values.projectId ?? 'project-1',
    name: values.name ?? 'Test Task',
    status: values.status ?? 'in_progress',
    sourceBranch: values.sourceBranch ?? null,
    taskBranch: values.taskBranch ?? null,
    linkedIssue: values.linkedIssue ?? null,
    archivedAt: values.archivedAt ?? null,
    deletedAt: values.deletedAt ?? null,
    createdAt: values.createdAt ?? '2026-05-18 12:00:00',
    updatedAt: values.updatedAt ?? '2026-05-18 12:00:00',
    lastInteractedAt: values.lastInteractedAt ?? null,
    statusChangedAt: values.statusChangedAt ?? '2026-05-18 12:00:00',
    isPinned: values.isPinned ?? 0,
    workspaceId: values.workspaceId ?? null,
    type: values.type ?? 'task',
    automationRunId: values.automationRunId ?? null,
  };
}

/**
 * Sets up db.transaction to invoke the callback with a fake `tx`.
 * The fake tx captures insert values by call order (0=task, 1=workspace if any, 2=conversation).
 * Returns an array that is populated with each set of insert values as the callback runs.
 */
function setupTransactionMock() {
  const captured: unknown[] = [];

  mocks.transaction.mockImplementation((cb: (tx: unknown) => void) => {
    captured.length = 0;
    return cb(fakeTx(captured));
  });

  return { captured };
}

function fakeTx(captured: unknown[]) {
  return {
    insert: () => ({
      values: (vals: unknown) => {
        captured.push(vals);
        const returning = () => ({
          all: () => [makeTaskRow(vals as Partial<TaskRow>)],
          get: () => vals,
        });
        return {
          returning,
          // The conversation registry registers via an id-conflict upsert.
          onConflictDoUpdate: () => ({ returning }),
          run: () => {},
        };
      },
    }),
    update: () => ({
      set: () => ({ where: () => ({ run: () => ({ changes: 1 }) }) }),
    }),
    delete: () => ({ where: () => ({ run: () => ({ changes: 1 }) }) }),
    // Conversation-registry purge checks that no live (tracked) rows remain first.
    select: () => ({ from: () => ({ where: () => ({ all: () => [] }) }) }),
  };
}

/** Sets up db.select to return the project row's repository workspace link. */
function setupSelectMock() {
  mocks.select.mockImplementation((selection?: unknown) =>
    selection
      ? {
          from: () => ({
            where: () => ({
              limit: () => Promise.resolve([{ repositoryWorkspaceId: 'repo-workspace' }]),
            }),
          }),
        }
      : {
          from: () => ({
            where: () => ({
              limit: () => ({
                get: () => mocks.registryRows.shift(),
                all: () => {
                  const row = mocks.registryRows.shift();
                  return row === undefined ? [] : [row];
                },
              }),
            }),
          }),
        }
  );
}

/** Points the project session mock at a remote (SSH) host. */
function makeProjectRemote() {
  mocks.getProject.mockReturnValue({
    project: { id: 'project-1', path: '/repo' },
    repoPath: '/repo',
    host: hostRef('remote', 'conn-1'),
    workspaceRegistry,
    gitRepository: {
      getBaseRemote: vi.fn(async () => 'origin'),
      getEffectiveRemotes: vi.fn(async () => ({ baseRemote: 'origin', pushRemote: 'fork' })),
    },
  });
}

describe('createTask', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    projectConfig.preservePatterns = ['.env'];
    creations = new WorkspaceCreations();
    mocks.getProject.mockReturnValue({
      project: { id: 'project-1', path: '/repo' },
      repoPath: '/repo',
      host: hostRef('local', 'local'),
      workspaceRegistry,
      gitRepository: {
        getBaseRemote: vi.fn(async () => 'origin'),
        getEffectiveRemotes: vi.fn(async () => ({ baseRemote: 'origin', pushRemote: 'fork' })),
      },
    });
    mocks.requireAttached.mockImplementation(() => {
      const project = mocks.getProject();
      return project
        ? { success: true as const, data: project }
        : {
            success: false as const,
            error: { type: 'project-missing' as const, projectId: 'project-1' },
          };
    });
    mocks.findWorkspaceTombstoneConflict.mockReturnValue(undefined);
    mocks.resolveProjectWorkspaceTarget.mockResolvedValue({
      success: true,
      data: { id: 'ws-repo-1', path: '/repo' },
    });
    mocks.hostIsReachable.mockReturnValue(true);
    mocks.resolveWorktreeRoot.mockResolvedValue({ success: true, data: '/worktrees' });
    mocks.registryRows.length = 0;
    setupTransactionMock();
    setupSelectMock();
  });

  it('returns project-not-found when project does not exist', async () => {
    mocks.getProject.mockReturnValue(undefined);
    const result = await createTask(db, projects, hostIsReachable, {
      id: 'task-1',
      projectId: 'project-1',
      taskConfig: { version: '1', name: 'Test Task' },
      workspaceConfig: {
        version: '2',
        git: { kind: 'none' },
        workspace: { kind: 'repository-instance', workspaceId: 'ws-repo-1' },
      },
    });
    expect(result).toEqual({ success: false, error: { type: 'project-not-found' } });
    expect(mocks.transaction).not.toHaveBeenCalled();
  });

  describe('tombstone-aware creation admission (ADR 0006)', () => {
    it('refuses a repository-instance target carrying a pending tombstone', async () => {
      mocks.findWorkspaceTombstoneConflict.mockReturnValue({
        type: 'workspace-tombstone-pending',
        workspaceId: 'ws-repo-1',
        message: 'This workspace is pending deletion on its host.',
      });

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: { kind: 'none' },
          workspace: { kind: 'repository-instance', workspaceId: 'ws-repo-1' },
        },
      });

      expect(result).toEqual({
        success: false,
        error: {
          type: 'workspace-tombstone-pending',
          workspaceId: 'ws-repo-1',
          message: 'This workspace is pending deletion on its host.',
        },
      });
      expect(mocks.findWorkspaceTombstoneConflict).toHaveBeenCalledWith(db, {
        kind: 'workspace',
        workspaceId: 'ws-repo-1',
      });
      expect(mocks.transaction).not.toHaveBeenCalled();
    });

    it('checks the branch as a placement target for new worktrees', async () => {
      makeProjectRemote();
      mocks.findWorkspaceTombstoneConflict.mockReturnValue({
        type: 'workspace-tombstone-pending',
        workspaceId: 'ws-old',
        message: 'A deletion is still pending for branch "feature/x".',
      });

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/x',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      expect(result.success).toBe(false);
      if (!result.success) expect(result.error.type).toBe('workspace-tombstone-pending');
      expect(mocks.findWorkspaceTombstoneConflict).toHaveBeenCalledWith(db, {
        kind: 'placement',
        location: 'remote',
        sshConnectionId: 'conn-1',
        branch: 'feature/x',
      });
      expect(workspaceRegistry.createWorktree).not.toHaveBeenCalled();
      expect(mocks.transaction).not.toHaveBeenCalled();
    });

    it('refuses a worktree path carrying a pending tombstone instead of suffixing', async () => {
      const conflict = {
        type: 'workspace-tombstone-pending' as const,
        workspaceId: 'ws-held',
        message: 'A deletion is still pending at /worktrees/repo/feature-test.',
      };
      mocks.findWorkspaceTombstoneConflict.mockImplementation(
        (_db: unknown, target: { path?: string }) =>
          target.path !== undefined ? conflict : undefined
      );

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/test',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      expect(result).toEqual({ success: false, error: conflict });
      expect(mocks.findWorkspaceTombstoneConflict).toHaveBeenCalledWith(db, {
        kind: 'placement',
        location: 'local',
        sshConnectionId: null,
        path: expect.stringMatching(/^\/worktrees\/repo-[a-f0-9]{8}\/feature-test$/u),
      });
      // No silent side-step: nothing is allocated, registered, or committed.
      expect(workspaceRegistry.createWorktree).not.toHaveBeenCalled();
      expect(mocks.transaction).not.toHaveBeenCalled();
    });

    it('suffixes past a genuine live-row collision but refuses a tombstone-pending candidate', async () => {
      // The base path is occupied by a live, non-tombstoned row; the suffixed
      // candidate is held by a pending deletion tombstone.
      mocks.registryRows.push({ id: 'existing' });
      const conflict = {
        type: 'workspace-tombstone-pending' as const,
        workspaceId: 'ws-held',
        message: 'A deletion is still pending at /worktrees/repo/feature-test-2.',
      };
      mocks.findWorkspaceTombstoneConflict.mockImplementation(
        (_db: unknown, target: { path?: string }) =>
          target.path?.endsWith('-2') ? conflict : undefined
      );

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/test',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      expect(result).toEqual({ success: false, error: conflict });
      expect(workspaceRegistry.createWorktree).not.toHaveBeenCalled();
      expect(mocks.transaction).not.toHaveBeenCalled();
    });
  });

  it('executes all writes inside a single db.transaction call', async () => {
    await createTask(db, projects, hostIsReachable, {
      id: 'task-1',
      projectId: 'project-1',
      taskConfig: { version: '1', name: 'Test Task' },
      workspaceConfig: {
        version: '2',
        git: { kind: 'none' },
        workspace: { kind: 'repository-instance', workspaceId: 'ws-repo-1' },
      },
    });
    expect(mocks.transaction).toHaveBeenCalledTimes(1);
  });

  it('does not write taskBranch or sourceBranch to the tasks row', async () => {
    const { captured } = setupTransactionMock();

    await createTask(db, projects, hostIsReachable, {
      id: 'task-1',
      projectId: 'project-1',
      taskConfig: { version: '1', name: 'Test Task' },
      workspaceConfig: {
        version: '2',
        git: {
          kind: 'create-branch',
          branchName: 'feature/x',
          fromBranch: { type: 'local', branch: 'main' },
        },
        workspace: { kind: 'new-worktree' },
      },
    });

    const taskInsert = captured[0] as Record<string, unknown>;
    expect(taskInsert).not.toEqual(
      expect.objectContaining({ taskBranch: expect.anything(), sourceBranch: expect.anything() })
    );
  });

  it('includes workspaceId in the task row insert', async () => {
    const { captured } = setupTransactionMock();

    await createTask(db, projects, hostIsReachable, {
      id: 'task-1',
      projectId: 'project-1',
      taskConfig: { version: '1', name: 'Test Task' },
      workspaceConfig: {
        version: '2',
        git: { kind: 'none' },
        workspace: { kind: 'repository-instance', workspaceId: 'ws-repo-1' },
      },
    });

    const taskInsert = captured[0] as Record<string, unknown>;
    expect(taskInsert.workspaceId).toBeDefined();
    expect(typeof taskInsert.workspaceId).toBe('string');
  });

  describe('repository-instance workspace target', () => {
    it('refuses a workspace that is unavailable to the project', async () => {
      mocks.resolveProjectWorkspaceTarget.mockResolvedValue({
        success: false,
        error: {
          type: 'workspace-unavailable',
          workspaceId: 'ws-other',
          message: 'The selected workspace does not belong to this project.',
        },
      });

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: { kind: 'none' },
          workspace: { kind: 'repository-instance', workspaceId: 'ws-other' },
        },
      });

      expect(result).toEqual({
        success: false,
        error: {
          type: 'workspace-unavailable',
          workspaceId: 'ws-other',
          message: 'The selected workspace does not belong to this project.',
        },
      });
      expect(mocks.transaction).not.toHaveBeenCalled();
    });

    it('reuses the existing workspace ID from config', async () => {
      const { captured } = setupTransactionMock();
      await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: { kind: 'none' },
          workspace: { kind: 'repository-instance', workspaceId: 'ws-repo-1' },
        },
      });

      // Only the task row is inserted — no workspace insert.
      expect(captured).toHaveLength(1);
      expect((captured[0] as Record<string, unknown>).workspaceId).toBe('ws-repo-1');
    });

    it('does not call the registry verbs', async () => {
      await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: { kind: 'none' },
          workspace: { kind: 'repository-instance', workspaceId: 'ws-repo-1' },
        },
      });

      expect(workspaceRegistry.createWorkspace).not.toHaveBeenCalled();
      expect(workspaceRegistry.createWorktree).not.toHaveBeenCalled();
    });
  });

  describe('new-worktree workspace target', () => {
    it('inserts a workspace row and runs the registry verbs with the compiled spec', async () => {
      const { captured } = setupTransactionMock();
      const workspaceConfig = {
        version: '2' as const,
        git: {
          kind: 'create-branch' as const,
          branchName: 'feature/test',
          fromBranch: { type: 'local' as const, branch: 'main' },
          pushBranch: true,
        },
        workspace: { kind: 'new-worktree' as const },
      };

      await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig,
      });

      // captured[0]=task, captured[1]=workspace
      expect(captured).toHaveLength(2);
      const wsInsert = captured[1] as Record<string, unknown>;
      expect(wsInsert.kind).toBe('worktree');
      expect(wsInsert.location).toBe('local');
      expect(wsInsert.origin).toBe('registered');
      expect(wsInsert.config).toEqual(workspaceConfig);
      expect(wsInsert.path).toMatch(/^\/worktrees\/repo-[a-f0-9]{8}\/feature-test$/u);
      expect(wsInsert.key).toBeUndefined();

      await settleCreation(wsInsert.id);
      // The project row already links a repository workspace; it is re-registered
      // idempotently under its preserved id before the worktree verb runs.
      expect(workspaceRegistry.createWorkspace).toHaveBeenCalledWith({
        workspaceId: 'repo-workspace',
        path: '/repo',
      });
      expect(workspaceRegistry.createWorktree).toHaveBeenCalledWith({
        workspaceId: wsInsert.id,
        repositoryId: 'repo-workspace',
        branch: 'feature/test',
        baseRef: 'main',
        path: wsInsert.path,
        preservePatterns: ['.env'],
        publish: { remote: 'fork' },
      });
    });

    it('does not request a push when pushBranch is not set', async () => {
      const { captured } = setupTransactionMock();

      await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/no-push',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      await settleCreation((captured[1] as Record<string, unknown>).id);
      const input = workspaceRegistry.createWorktree.mock.calls[0][0];
      expect(input).not.toHaveProperty('publish');
    });

    it('refuses a requested push when the resolver finds no push remote', async () => {
      const project = mocks.getProject() as { gitRepository: { getEffectiveRemotes: Mock } };
      project.gitRepository.getEffectiveRemotes.mockResolvedValue({
        baseRemote: 'origin',
        pushRemote: null,
      });

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/no-push-remote',
            fromBranch: { type: 'local', branch: 'main' },
            pushBranch: true,
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      expect(result).toEqual({
        success: false,
        error: {
          type: 'provision-failed',
          message: 'Cannot publish the task branch because the repository has no push remote.',
        },
      });
      expect(mocks.transaction).not.toHaveBeenCalled();
    });

    it('passes empty resolved preservePatterns to worktree creation', async () => {
      projectConfig.preservePatterns = [];
      const { captured } = setupTransactionMock();

      await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/no-artifacts',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      await settleCreation((captured[1] as Record<string, unknown>).id);
      expect(workspaceRegistry.createWorktree).toHaveBeenCalledWith(
        expect.objectContaining({ preservePatterns: [] })
      );
    });

    it('compiles a remote fromBranch into a remote-qualified baseRef', async () => {
      const { captured } = setupTransactionMock();

      await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/remote',
            fromBranch: {
              type: 'remote',
              branch: 'main',
              remote: { name: 'origin', url: 'git@example.com:repo.git' },
            },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      await settleCreation((captured[1] as Record<string, unknown>).id);
      expect(workspaceRegistry.createWorktree).toHaveBeenCalledWith(
        expect.objectContaining({ baseRef: 'origin/main' })
      );
    });

    it('sets location=remote and type=project-ssh for SSH projects', async () => {
      makeProjectRemote();
      const { captured } = setupTransactionMock();

      await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/ssh',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      const wsInsert = captured[1] as Record<string, unknown>;
      expect(wsInsert.kind).toBe('worktree');
      expect(wsInsert.location).toBe('remote');
      expect(wsInsert.type).toBe('project-ssh');
      expect(wsInsert.sshConnectionId).toBe('conn-1');
      await settleCreation(wsInsert.id);
    });

    it('refuses creation when effective Project attachment is unavailable', async () => {
      makeProjectRemote();
      mocks.requireAttached.mockReturnValue({
        success: false,
        error: {
          type: 'attachment-unavailable',
          host: hostRef('remote', 'conn-1'),
          phase: 'waiting',
        },
      });
      const { captured } = setupTransactionMock();

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/ssh',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error).toEqual({
          type: 'project-unavailable',
          reason: 'attachment-unavailable',
          message: 'This action requires live Project access.',
        });
      }
      expect(mocks.hostIsReachable).not.toHaveBeenCalled();
      expect(captured).toHaveLength(0);
    });

    it('suffixes paths against live Registry rows without probing the host', async () => {
      mocks.registryRows.push({ id: 'existing' });
      const { captured } = setupTransactionMock();

      await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/test',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      await settleCreation((captured[1] as Record<string, unknown>).id);
      expect(workspaceRegistry.createWorktree).toHaveBeenCalledWith(
        expect.objectContaining({
          path: expect.stringMatching(/\/feature-test-2$/u),
        })
      );
    });

    it('refuses repository-instance creation without effective Project attachment', async () => {
      makeProjectRemote();
      mocks.requireAttached.mockReturnValue({
        success: false,
        error: {
          type: 'attachment-unavailable',
          host: hostRef('remote', 'conn-1'),
          phase: 'waiting',
        },
      });
      const { captured } = setupTransactionMock();

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: { kind: 'none' },
          workspace: { kind: 'repository-instance', workspaceId: 'ws-repo-1' },
        },
      });

      // One rule (spec §6.3): this path was previously ungated because it only
      // wrote client SQLite; under host residency it refuses like new-worktree.
      expect(result.success).toBe(false);
      expect(captured).toHaveLength(0);
      expect(mocks.transaction).not.toHaveBeenCalled();
    });

    it('commits the task even when the background worktree creation fails', async () => {
      const { captured } = setupTransactionMock();
      workspaceRegistry.createWorktree.mockResolvedValueOnce({
        success: false,
        error: { type: 'stage-failed', stage: 'add-worktree', message: 'branch exists' },
      } as never);

      const result = await createTask(db, projects, hostIsReachable, {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1', name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'feature/test',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });

      // The verb failure is durable on the host record (ADR 0005); desktop rows stay
      // and provisioning surfaces the failure from the pending creation outcome.
      expect(result.success).toBe(true);
      const wsInsert = captured[1] as Record<string, unknown>;
      const outcome = await creations.pending(String(wsInsert.id));
      expect(outcome).toEqual({
        success: false,
        error: { stage: 'add-worktree', message: 'branch exists' },
      });
    });
  });

  describe('PR-sourced presets (pr-workspace-model)', () => {
    // The desktop harness mocks the registry client, so these tests pin the seam:
    // the exact compiled verb input. The host-side execution of gitSetup is
    // integration-tested in packages/core workspace-registry create-worktree tests.
    function prParams(git: Record<string, unknown>) {
      return {
        id: 'task-1',
        projectId: 'project-1',
        taskConfig: { version: '1' as const, name: 'Test Task' },
        workspaceConfig: {
          version: '2',
          git: {
            kind: 'pr-branch',
            prUrl: 'https://github.com/org/repo/pull/42',
            prNumber: 42,
            headBranch: 'feat/my-pr',
            headRepositoryUrl: 'https://github.com/org/repo',
            isFork: false,
            ...git,
          },
          workspace: { kind: 'new-worktree' },
        } as never,
      };
    }

    it('compiles same-repo checkout-pr into fetch + upstream on the head branch', async () => {
      const { captured } = setupTransactionMock();

      await createTask(db, projects, hostIsReachable, prParams({}));

      const wsInsert = captured[1] as Record<string, unknown>;
      await settleCreation(wsInsert.id);
      expect(workspaceRegistry.createWorktree).toHaveBeenCalledWith({
        workspaceId: wsInsert.id,
        repositoryId: 'repo-workspace',
        branch: 'feat/my-pr',
        path: wsInsert.path,
        preservePatterns: ['.env'],
        gitSetup: {
          fetchBranch: { remote: 'origin', sourceRef: 'refs/heads/feat/my-pr' },
          upstream: { remote: 'origin', mergeRef: 'refs/heads/feat/my-pr' },
          breadcrumb: { prUrl: 'https://github.com/org/repo/pull/42' },
          followRef: true,
        },
      });
      // baseRef is omitted: fetchBranch materializes the branch.
      const verbInput = workspaceRegistry.createWorktree.mock.calls[0][0];
      expect('baseRef' in verbInput).toBe(false);
    });

    it('compiles fork checkout-pr into the namespaced branch fetched from the PR ref', async () => {
      const { captured } = setupTransactionMock();

      await createTask(
        db,
        projects,
        hostIsReachable,
        prParams({ isFork: true, headRepositoryUrl: 'https://github.com/fork/repo' })
      );

      const wsInsert = captured[1] as Record<string, unknown>;
      await settleCreation(wsInsert.id);
      expect(wsInsert.path).toMatch(/\/pr-42-feat-my-pr$/u);
      expect(workspaceRegistry.createWorktree).toHaveBeenCalledWith(
        expect.objectContaining({
          branch: 'pr/42/feat/my-pr',
          gitSetup: {
            fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/42/head' },
            upstream: { remote: 'origin', mergeRef: 'refs/pull/42/head' },
            breadcrumb: { prUrl: 'https://github.com/org/repo/pull/42' },
            followRef: true,
          },
        })
      );
    });

    it('refuses PR checkout when the resolver finds no remotes', async () => {
      // The effective base remote comes from the blessed resolver; null means
      // the repository has no remotes, so a PR-sourced plan cannot compile.
      const project = mocks.getProject() as { gitRepository: { getEffectiveRemotes: Mock } };
      project.gitRepository.getEffectiveRemotes.mockResolvedValue({
        baseRemote: null,
        pushRemote: null,
      });

      const result = await createTask(db, projects, hostIsReachable, prParams({}));

      expect(result).toEqual({
        success: false,
        error: {
          type: 'provision-failed',
          message: 'The repository has no git remotes, so a pull request cannot be checked out.',
        },
      });
      expect(mocks.transaction).not.toHaveBeenCalled();
    });

    it('compiles pr-new-branch into the task branch with no gitSetup upstream and a push', async () => {
      const { captured } = setupTransactionMock();

      await createTask(
        db,
        projects,
        hostIsReachable,
        prParams({ taskBranch: 'task/42', pushBranch: true })
      );

      const wsInsert = captured[1] as Record<string, unknown>;
      await settleCreation(wsInsert.id);
      expect(workspaceRegistry.createWorktree).toHaveBeenCalledWith(
        expect.objectContaining({
          branch: 'task/42',
          publish: { remote: 'fork' },
          gitSetup: {
            fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/42/head' },
            breadcrumb: { prUrl: 'https://github.com/org/repo/pull/42' },
            followRef: true,
          },
        })
      );
    });
  });

  describe('host-first conversation record (spec §6.2)', () => {
    const worktreeParams = {
      id: 'task-1',
      projectId: 'project-1',
      taskConfig: {
        version: '1' as const,
        name: 'Test Task',
        initialConversation: {
          id: 'conv-1',
          provider: 'claude-code',
          type: 'acp' as const,
          title: 'First conversation',
          initialQueue: [{ text: 'do the thing' }],
        },
      },
      workspaceConfig: {
        version: '2' as const,
        git: {
          kind: 'create-branch' as const,
          branchName: 'feature/test',
          fromBranch: { type: 'local' as const, branch: 'main' },
        },
        workspace: { kind: 'new-worktree' as const },
      },
    };

    it('registers the record on the host before the desktop commit, path frozen and prompt in config', async () => {
      const { captured } = setupTransactionMock();

      const result = await createTask(db, projects, hostIsReachable, worktreeParams);
      expect(result.success).toBe(true);

      expect(hostConversations.create).toHaveBeenCalledTimes(1);
      const hostInput = hostConversations.create.mock.calls[0][0] as Record<string, unknown>;
      const wsInsert = captured[1] as Record<string, unknown>;
      await settleCreation(wsInsert.id);
      const verbInput = workspaceRegistry.createWorktree.mock.calls[0][0];
      // conv.path-frozen: the record is born dangling with the Placement-computed
      // path already frozen — identical to the path the worktree verb (and any
      // same-path retry of it) will materialize.
      expect(hostInput.workspacePath).toBe(verbInput.path);
      expect(hostInput.cwd).toBe(verbInput.path);
      expect(hostInput).toMatchObject({
        conversationId: 'conv-1',
        provider: 'claude-code',
        type: 'acp',
        idRegime: 'provider-minted',
        title: 'First conversation',
        config: expect.objectContaining({ initialQueue: [{ text: 'do the thing' }] }),
      });
      // Host-first ordering: index registration precedes the desktop transaction.
      expect(hostConversations.create.mock.invocationCallOrder[0]).toBeLessThan(
        mocks.transaction.mock.invocationCallOrder[0]
      );
    });

    it('fails creation without a desktop commit when host registration fails', async () => {
      setupTransactionMock();
      hostConversations.create.mockResolvedValueOnce({
        success: false,
        error: { type: 'immutable-field-mismatch', message: 'id reuse' },
      } as never);

      const result = await createTask(db, projects, hostIsReachable, worktreeParams);

      expect(result).toEqual({
        success: false,
        error: { type: 'provision-failed', message: 'id reuse' },
      });
      expect(mocks.transaction).not.toHaveBeenCalled();
      expect(workspaceRegistry.createWorktree).not.toHaveBeenCalled();
      expect(hostConversations.delete).not.toHaveBeenCalled();
    });

    it('compensates with a direct foreground delete when the desktop commit fails', async () => {
      mocks.transaction.mockImplementationOnce(() => {
        throw new Error('constraint violated');
      });

      await expect(createTask(db, projects, hostIsReachable, worktreeParams)).rejects.toThrow(
        'constraint violated'
      );
      expect(hostConversations.delete).toHaveBeenCalledWith({ conversationId: 'conv-1' });
      expect(workspaceRegistry.createWorktree).not.toHaveBeenCalled();
    });

    it('freezes the existing workspace path for repository-instance targets', async () => {
      const { captured } = setupTransactionMock();
      mocks.registryRows.push({ id: 'ws-repo-1', path: '/repo' });

      const result = await createTask(db, projects, hostIsReachable, {
        ...worktreeParams,
        taskConfig: {
          ...worktreeParams.taskConfig,
          initialConversation: {
            ...worktreeParams.taskConfig.initialConversation,
            type: 'pty' as const,
            initialQueue: undefined,
            initialPrompt: 'do the thing',
          },
        },
        workspaceConfig: {
          version: '2',
          git: { kind: 'none' },
          workspace: { kind: 'repository-instance', workspaceId: 'ws-repo-1' },
        },
      });
      expect(result.success).toBe(true);

      const hostInput = hostConversations.create.mock.calls[0][0] as Record<string, unknown>;
      expect(hostInput).toMatchObject({
        workspacePath: '/repo',
        cwd: '/repo',
        idRegime: 'emdash-chosen',
        config: expect.objectContaining({ initialPrompt: 'do the thing' }),
      });
      // captured[0]=task, captured[1]=conversation registry row with the same frozen path.
      const convInsert = captured[1] as Record<string, unknown>;
      expect(convInsert).toMatchObject({ id: 'conv-1', workspacePath: '/repo', cwd: '/repo' });
    });
  });
});
