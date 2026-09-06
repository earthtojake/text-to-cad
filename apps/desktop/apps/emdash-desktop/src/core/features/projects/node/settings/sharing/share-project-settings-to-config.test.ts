import { err, ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import type { ShareableProjectSettings } from '@core/primitives/project-settings/api';
import { filesClientScope, type FilesClientScope } from '@core/services/runtime-broker/node/files';
import {
  getProjectSettingsWriteTargets,
  resolveAllProjectSettingsTargets,
} from './project-settings-target-resolver';
import { shareProjectSettingsToConfig } from './share-project-settings-to-config';

const mocks = vi.hoisted(() => ({
  select: vi.fn(),
  workspaceGet: vi.fn(),
}));

const db = { select: mocks.select } as never;
const workspaceIdentity = { resolve: mocks.workspaceGet } as never;

vi.mock('../utils', () => ({
  resolveWorkspace: vi.fn().mockReturnValue(null),
}));

vi.mock('@emdash/shared/logger', () => {
  const log = {
    child: vi.fn(),
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  };
  log.child.mockImplementation(() => log);
  return { log };
});

const repoPath = '/repo';
const configPath = `${repoPath}/.emdash.json`;

function createMemoryFileSystem(initialFiles: Record<string, string> = {}) {
  const files = new Map(
    Object.entries(initialFiles).map(([filePath, content]) => [
      filePath.startsWith('/') ? filePath : `${repoPath}/${filePath}`,
      content,
    ])
  );
  const exists = vi.fn(async (filePath: string) => ok({ exists: files.has(filePath) }));
  const readText = vi.fn(async (filePath: string) => {
    const content = files.get(filePath);
    if (content === undefined) {
      return err({
        type: 'not-found' as const,
        path: filePath,
      });
    }
    return ok({
      content,
      truncated: false,
      totalSize: Buffer.byteLength(content),
      etag: 'test-etag',
    });
  });
  const writeText = vi.fn(async (filePath: string, content: string) => {
    files.set(filePath, content);
    return ok({ bytesWritten: Buffer.byteLength(content) });
  });
  const clientReadText = vi.fn(({ path }: { path: Parameters<typeof nativePathFromHost>[0] }) =>
    readText(nativePathFromHost(path))
  );
  const writeFile = vi.fn(
    ({ path, content }: { path: Parameters<typeof nativePathFromHost>[0]; content: string }) =>
      writeText(nativePathFromHost(path), content).then((result) =>
        result.success ? ok(undefined) : result
      )
  );
  const scope = filesClientScope(
    {
      fs: {
        exists: ({ path }: { path: Parameters<typeof nativePathFromHost>[0] }) =>
          exists(nativePathFromHost(path)),
        readText: clientReadText,
        writeFile,
      },
    } as never,
    repoPath
  );
  return Object.assign(scope, {
    exists,
    readText,
    writeText,
    content(filePath: string) {
      return files.get(filePath) ?? files.get(`${repoPath}/${filePath}`);
    },
  });
}

function joinPath(...parts: string[]): string {
  return parts.join('/').replace(/\/+/g, '/');
}

function configPathForDirectory(directoryPath: string): string {
  return joinPath(directoryPath, '.emdash.json');
}

function projectFixture(files: FilesClientScope, overrides: Record<string, unknown> = {}) {
  return {
    projectId: 'project-1',
    repoPath,
    files,
    projectConfigPath: configPath,
    resolveProjectPath: (relativePath: string) => joinPath(repoPath, relativePath),
    configPathForDirectory,
    defaultWorkspaceType: { kind: 'local' },
    ...overrides,
  };
}

function projectTarget(files: FilesClientScope) {
  return { type: 'project' as const, label: 'Repo Name', path: repoPath, files, configPath };
}

describe('shareProjectSettingsToConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.workspaceGet.mockReturnValue(undefined);
  });

  it('writes selected shareable project settings to .emdash.json', async () => {
    const fileSystem = createMemoryFileSystem();
    const write = fileSystem.writeText;
    const localSettings = {
      preservePatterns: ['.env', '.env.local'],
      scripts: {
        setup: 'pnpm install',
        run: 'pnpm dev',
      },
    };

    const result = await shareProjectSettingsToConfig(
      projectTarget(fileSystem),
      ['preservePatterns', 'scripts.setup', 'scripts.run'],
      localSettings
    );

    expect(result).toEqual({
      success: true,
      data: ['preservePatterns', 'scripts.setup', 'scripts.run'],
    });
    expect(write).toHaveBeenCalledWith(
      configPath,
      `${JSON.stringify(
        {
          preservePatterns: ['.env', '.env.local'],
          scripts: {
            setup: 'pnpm install',
            run: 'pnpm dev',
          },
        },
        null,
        2
      )}\n`
    );
  });

  it('writes supplied personal settings and returns exactly the written fields', async () => {
    const fileSystem = createMemoryFileSystem();
    const result = await shareProjectSettingsToConfig(
      projectTarget(fileSystem),
      ['preservePatterns', 'scripts.prepare', 'scripts.run'],
      {
        preservePatterns: [],
        scripts: { prepare: 'pnpm install', run: 'pnpm dev' },
      }
    );

    expect(result).toEqual({
      success: true,
      data: ['preservePatterns', 'scripts.prepare', 'scripts.run'],
    });
    expect(JSON.parse(fileSystem.content('.emdash.json') ?? '{}')).toEqual({
      preservePatterns: [],
      scripts: { prepare: 'pnpm install', run: 'pnpm dev' },
    });
  });

  it('preserves existing config fields when sharing a later script field to the same target', async () => {
    const fileSystem = createMemoryFileSystem();
    let shareableSettings: ShareableProjectSettings = {
      preservePatterns: ['.env', '.env.local'],
    };
    const target = projectTarget(fileSystem);

    await shareProjectSettingsToConfig(target, ['preservePatterns'], shareableSettings);

    shareableSettings = {
      scripts: {
        run: 'pnpm dev',
      },
    };

    const result = await shareProjectSettingsToConfig(target, ['scripts.run'], shareableSettings);

    expect(result.success).toBe(true);
    expect(JSON.parse(fileSystem.content('.emdash.json') ?? '{}')).toEqual({
      preservePatterns: ['.env', '.env.local'],
      scripts: {
        run: 'pnpm dev',
      },
    });
  });

  it('only returns fields that were actually written to .emdash.json', async () => {
    const fileSystem = createMemoryFileSystem({
      '.emdash.json': JSON.stringify({ preservePatterns: ['.env'] }),
    });
    const write = fileSystem.writeText;

    const result = await shareProjectSettingsToConfig(
      projectTarget(fileSystem),
      ['preservePatterns', 'scripts.run'],
      { preservePatterns: ['.env.local'] }
    );

    expect(result).toEqual({ success: true, data: ['preservePatterns'] });
    expect(write).toHaveBeenCalledWith(
      configPath,
      `${JSON.stringify({ preservePatterns: ['.env.local'] }, null, 2)}\n`
    );
  });

  it('returns an error when the filesystem reports an unsuccessful write', async () => {
    const fileSystem = createMemoryFileSystem();
    vi.mocked(fileSystem.client.fs.writeFile).mockResolvedValue(
      err({ type: 'io' as const, path: '.emdash.json', message: 'permission denied' })
    );

    const result = await shareProjectSettingsToConfig(
      projectTarget(fileSystem),
      ['preservePatterns'],
      { preservePatterns: ['.env'] }
    );

    expect(result).toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message: 'Could not write .emdash.json: permission denied',
      },
    });
  });

  it('returns the read/parse failure when existing .emdash.json cannot be parsed', async () => {
    const fileSystem = createMemoryFileSystem({ '.emdash.json': '{ invalid json' });
    const result = await shareProjectSettingsToConfig(
      projectTarget(fileSystem),
      ['preservePatterns'],
      { preservePatterns: ['.env'] }
    );

    if (result.success) {
      throw new Error('Expected write to fail');
    }
    expect(result.error).toMatchObject({
      type: 'write-config-failed',
    });
    if (result.error.type !== 'write-config-failed') {
      throw new Error(`Unexpected error type: ${result.error.type}`);
    }
    expect(result.error.message).toContain('Could not read existing .emdash.json');
  });

  it('does not overwrite an existing .emdash.json when the read is truncated', async () => {
    const fileSystem = createMemoryFileSystem({ '.emdash.json': '{"shellSetup":' });
    vi.mocked(fileSystem.client.fs.readText).mockResolvedValue(
      ok({
        content: '{"shellSetup":',
        truncated: true,
        totalSize: 204_801,
        etag: 'test-etag',
      })
    );
    const result = await shareProjectSettingsToConfig(
      projectTarget(fileSystem),
      ['preservePatterns'],
      { preservePatterns: ['.env'] }
    );

    expect(result).toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message: 'Could not read existing .emdash.json: file was truncated.',
      },
    });
    expect(fileSystem.writeText).not.toHaveBeenCalled();
  });

  it('includes task worktrees from git branch discovery, not only active workspaces', async () => {
    const findTaskWorktree = vi.fn().mockResolvedValue('/external/worktrees/task-one');
    const projectFs = createMemoryFileSystem();
    const project = projectFixture(projectFs, {
      findTaskWorktree,
    });
    mocks.select
      .mockReturnValueOnce({
        from: () => ({
          where: () => ({
            limit: vi.fn().mockResolvedValue([{ name: 'Repo Name' }]),
          }),
        }),
      })
      .mockReturnValueOnce({
        from: () => ({
          leftJoin: () => ({
            where: vi.fn().mockResolvedValue([
              {
                id: 'task-1',
                name: 'Task One',
                workspaceKind: 'worktree',
                workspaceConfig: {
                  version: '2',
                  git: { kind: 'use-branch', branchName: 'emdash/task-one' },
                  workspace: { kind: 'new-worktree' },
                },
                workspaceId: null,
              },
            ]),
          }),
        }),
      });
    const targets = getProjectSettingsWriteTargets(
      await resolveAllProjectSettingsTargets(db, workspaceIdentity, project as never)
    );

    expect(targets).toEqual([
      {
        type: 'project',
        label: 'Repo Name',
        path: '/repo',
        configPath: '/repo/.emdash.json',
      },
      {
        type: 'task',
        taskId: 'task-1',
        label: 'Task One',
        path: '/external/worktrees/task-one',
        configPath: '/external/worktrees/task-one/.emdash.json',
      },
    ]);
    expect(findTaskWorktree).toHaveBeenCalledWith('refs/heads/emdash/task-one');
  });

  it('excludes task targets that use the project root working directory', async () => {
    const projectRootFs = createMemoryFileSystem({
      '.emdash.json': JSON.stringify({ scripts: { run: 'root run' } }),
      '/repo/.emdash/worktrees/task-two/.emdash.json': JSON.stringify({
        scripts: { run: 'worktree run' },
      }),
    });
    const findTaskWorktree = vi.fn();
    const project = projectFixture(projectRootFs, {
      findTaskWorktree,
    });
    mocks.workspaceGet.mockImplementation((workspaceId: string) => {
      if (workspaceId === 'root-workspace') {
        return { workspaceId, projectId: 'project-1', path: '/repo' };
      }
      if (workspaceId === 'worktree-workspace') {
        return {
          workspaceId,
          projectId: 'project-1',
          path: '/repo/.emdash/worktrees/task-two',
        };
      }
      return undefined;
    });
    mocks.select
      .mockReturnValueOnce({
        from: () => ({
          where: () => ({
            limit: vi.fn().mockResolvedValue([{ name: 'Repo Name' }]),
          }),
        }),
      })
      .mockReturnValueOnce({
        from: () => ({
          leftJoin: () => ({
            where: vi.fn().mockResolvedValue([
              {
                id: 'task-1',
                name: 'Root Task',
                workspaceKind: 'repository',
                workspaceConfig: null,
                workspaceId: 'root-workspace',
              },
              {
                id: 'task-2',
                name: 'Task Two',
                workspaceKind: 'worktree',
                workspaceConfig: {
                  version: '2',
                  git: { kind: 'use-branch', branchName: 'emdash/task-two' },
                  workspace: { kind: 'new-worktree' },
                },
                workspaceId: 'worktree-workspace',
              },
            ]),
          }),
        }),
      });

    const resolvedTargets = await resolveAllProjectSettingsTargets(
      db,
      workspaceIdentity,
      project as never
    );
    const targets = getProjectSettingsWriteTargets(resolvedTargets);
    expect(targets).toEqual([
      {
        type: 'project',
        label: 'Repo Name',
        path: '/repo',
        configPath: '/repo/.emdash.json',
      },
      {
        type: 'task',
        taskId: 'task-2',
        label: 'Task Two',
        path: '/repo/.emdash/worktrees/task-two',
        configPath: '/repo/.emdash/worktrees/task-two/.emdash.json',
        sourceWorkspaceId: 'worktree-workspace',
      },
    ]);
    expect(findTaskWorktree).not.toHaveBeenCalled();
  });

  it('skips task target resolution when the project row no longer exists', async () => {
    const findTaskWorktree = vi.fn();
    const projectFs = createMemoryFileSystem();
    const project = projectFixture(projectFs, {
      findTaskWorktree,
    });
    mocks.select.mockReturnValueOnce({
      from: () => ({
        where: () => ({
          limit: vi.fn().mockResolvedValue([]),
        }),
      }),
    });

    const targets = getProjectSettingsWriteTargets(
      await resolveAllProjectSettingsTargets(db, workspaceIdentity, project as never)
    );

    expect(targets).toEqual([
      {
        type: 'project',
        label: 'Project repository',
        path: '/repo',
        configPath: '/repo/.emdash.json',
      },
    ]);
    expect(mocks.select).toHaveBeenCalledTimes(1);
    expect(findTaskWorktree).not.toHaveBeenCalled();
  });
});
