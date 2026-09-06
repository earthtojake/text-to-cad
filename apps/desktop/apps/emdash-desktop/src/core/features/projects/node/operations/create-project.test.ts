import { ok } from '@emdash/shared';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import { createProject } from './create-project';
import { initializeRepository } from './initialize-repository';

const mocks = vi.hoisted(() => ({
  claimWorkspace: vi.fn(),
  registerRepositoryWorkspace: vi.fn(),
}));

vi.mock('@core/features/workspaces/api/node/registry', async (importOriginal) => ({
  ...(await importOriginal()),
  createWorkspaceRegistry: () => ({ claim: mocks.claimWorkspace }),
}));

vi.mock('./register-repository-workspace', () => ({
  registerRepositoryWorkspace: mocks.registerRepositoryWorkspace,
}));

describe('project creation without a git repository', () => {
  let rows: Record<string, unknown>[];
  let filesStat: ReturnType<typeof vi.fn>;
  let ensureRepository: ReturnType<typeof vi.fn>;
  let createWorkspace: ReturnType<typeof vi.fn>;
  let invalidate: ReturnType<typeof vi.fn>;
  let dependencies: Parameters<typeof initializeRepository>[0];

  beforeEach(() => {
    rows = [];
    filesStat = vi.fn().mockResolvedValue({
      success: true,
      data: { type: 'directory' },
    });
    ensureRepository = vi.fn();
    createWorkspace = vi.fn(async (input: { workspaceId: string; path: string }) =>
      ok(hostRecord(input.workspaceId, input.path))
    );
    invalidate = vi.fn().mockResolvedValue(undefined);
    mocks.claimWorkspace.mockImplementation((input) => ok(input.record));
    mocks.registerRepositoryWorkspace.mockImplementation((_db, input) => {
      const row = {
        ...input.project,
        repositoryWorkspaceId: input.record.id,
        createdAt: '2026-01-01T00:00:00.000Z',
        updatedAt: '2026-01-01T00:00:00.000Z',
        deletedAt: null,
      };
      rows.push(row);
      return ok(row);
    });
    dependencies = {
      db: createFakeDb(rows),
      runtimes: {
        client: vi.fn().mockResolvedValue({
          success: true,
          data: {
            files: { fs: { stat: filesStat } },
            git: { ensureRepository },
            workspaceRegistry: { createWorkspace },
          },
        }),
      },
      projects: { invalidate },
    } as unknown as Parameters<typeof initializeRepository>[0];
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('returns the durable Project without allocating an attachment after registration', async () => {
    ensureRepository.mockResolvedValue({
      success: false,
      error: { type: 'not-repository', path: hostPathFromNative('/workspace/plain-folder') },
    });
    const result = await createProject(dependencies, {
      type: 'local',
      id: 'project-plain',
      name: 'Plain Folder',
      path: '/workspace/plain-folder',
    });

    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.path).toBe('/workspace/plain-folder');
    // Creation provenance stays honestly absent for a non-git folder — no
    // fabricated 'main' (spec: github-git-settings §3).
    expect(result.data.baseRef).toBeNull();
    expect(result.data.repositoryWorkspaceId).toBeTruthy();

    const row = rows.find((entry) => entry.id === 'project-plain');
    expect(row?.baseRef).toBeNull();
  });

  it('initializes git for an existing project and persists the resolved base ref', async () => {
    rows.push({
      id: 'project-plain',
      name: 'Plain Folder',
      path: '/workspace/plain-folder',
      baseRef: null,
      repositoryWorkspaceId: 'repo-workspace-1',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
      deletedAt: null,
    });
    ensureRepository.mockResolvedValue({
      success: true,
      data: { rootPath: hostPathFromNative('/workspace/plain-folder'), baseRef: 'main' },
    });

    const result = await initializeRepository(dependencies, 'project-plain');

    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(ensureRepository).toHaveBeenCalledWith({
      path: hostPathFromNative('/workspace/plain-folder'),
      options: { initIfMissing: true },
    });
    expect(result.data.baseRef).toBe('main');
    expect(result.data.repositoryWorkspaceId).toBeTruthy();
    expect(invalidate).toHaveBeenCalledWith('project-plain', 'repository-changed');
    expect(createWorkspace).toHaveBeenCalledWith({
      workspaceId: 'repo-workspace-1',
      path: '/workspace/plain-folder',
    });
    expect(mocks.claimWorkspace).toHaveBeenCalledWith(
      expect.objectContaining({ record: expect.objectContaining({ id: 'repo-workspace-1' }) })
    );

    const row = rows.find((entry) => entry.id === 'project-plain');
    expect(row?.baseRef).toBe('main');
  });

  it('persists the canonical Workspace id returned by the Host', async () => {
    ensureRepository.mockResolvedValue({
      success: true,
      data: { rootPath: hostPathFromNative('/workspace/repository'), baseRef: 'main' },
    });
    createWorkspace.mockResolvedValueOnce(
      ok(hostRecord('host-canonical', '/workspace/repository'))
    );

    const result = await createProject(dependencies, {
      type: 'local',
      id: 'project-canonical',
      name: 'Canonical',
      path: '/workspace/repository',
    });

    expect(result).toMatchObject({
      success: true,
      data: { repositoryWorkspaceId: 'host-canonical' },
    });
    expect(mocks.registerRepositoryWorkspace).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ record: expect.objectContaining({ id: 'host-canonical' }) })
    );
  });
});

function hostRecord(id: string, path: string) {
  return {
    id,
    kind: 'repository' as const,
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
  };
}

function createFakeDb(rows: Record<string, unknown>[]) {
  const findRow = () => rows.find((row) => row.id === 'project-plain' && !row.deletedAt);
  return {
    insert: () => ({
      values: (value: Record<string, unknown>) => ({
        returning: async () => {
          const row = {
            repositoryWorkspaceId: null,
            createdAt: '2026-01-01T00:00:00.000Z',
            deletedAt: null,
            ...value,
            updatedAt: '2026-01-01T00:00:00.000Z',
          };
          rows.push(row);
          return [row];
        },
      }),
    }),
    // getProjectById joins the repository workspace row; the fake keeps the
    // path on the project row and projects it into the join columns.
    select: () => ({
      from: () => ({
        leftJoin: () => ({
          where: () => ({
            limit: async () => {
              const row = findRow();
              return row
                ? [
                    {
                      project: row,
                      repositoryPath: (row.path as string | undefined) ?? null,
                      repositoryLocation: 'local',
                      repositorySshConnectionId: null,
                    },
                  ]
                : [];
            },
          }),
        }),
      }),
    }),
    update: () => ({
      set: (value: Record<string, unknown>) => ({
        where: () => {
          const apply = () => {
            const row = findRow();
            if (!row) return undefined;
            Object.assign(row, value, { updatedAt: '2026-01-01T00:00:01.000Z' });
            return row;
          };
          return {
            then: (resolve: (value: unknown) => void) => resolve(apply()),
            run: () => {
              apply();
              return { changes: 1 };
            },
          };
        },
      }),
    }),
  } as unknown as Parameters<typeof createProject>[0]['db'];
}
