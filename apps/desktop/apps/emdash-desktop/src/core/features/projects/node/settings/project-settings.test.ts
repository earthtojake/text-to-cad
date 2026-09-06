import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { HostAbsolutePath } from '@emdash/core/primitives/path/api';
import { err, ok } from '@emdash/shared';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { filesClientScope } from '@core/services/runtime-broker/node/files';
import { migrateProjectSettingsOnAttachment } from './migrations/migrate-project-settings-on-attachment';
import type { ProjectSettingsStorage } from './project-settings-storage';
import { HostProjectSettingsProvider } from './providers/host-project-settings-provider';

const storageMockState = vi.hoisted(() => ({
  storage: undefined as ProjectSettingsStorage | undefined,
}));

function makeTrackingGit(isFileCleanlyTracked: boolean) {
  return {
    isFileCleanlyTracked: vi.fn().mockResolvedValue(isFileCleanlyTracked),
  };
}

const projectId = () => `project-${randomUUID()}`;

function makeLocalConfigFiles(projectPath: string) {
  const client = {
    fs: {
      exists: vi.fn(async ({ path: target }: { path: HostAbsolutePath }) =>
        ok({ exists: fs.existsSync(nativePathFromHost(target)) })
      ),
      readText: vi.fn(async ({ path: target }: { path: HostAbsolutePath }) => {
        try {
          const content = fs.readFileSync(nativePathFromHost(target), 'utf8');
          return ok({
            content,
            truncated: false,
            totalSize: Buffer.byteLength(content),
            etag: 'test-etag',
          });
        } catch {
          return err({ type: 'not-found' as const, path: nativePathFromHost(target) });
        }
      }),
    },
  };
  return filesClientScope(client as never, projectPath);
}

function makeLocalProvider(
  projectPath: string,
  options?: Partial<
    Omit<
      ConstructorParameters<typeof HostProjectSettingsProvider>[4],
      'worktreeDirectoryFileSystem'
    >
  >,
  id = projectId()
): HostProjectSettingsProvider {
  return new HostProjectSettingsProvider(
    id,
    projectPath,
    'main',
    makeLocalConfigFiles(projectPath),
    {
      placementContext: () =>
        Promise.resolve({
          hostWorktreeRoot: '/tmp/emdash/worktrees',
          builtInWorktreeRoot: '/tmp/emdash/worktrees',
          homeDirectory: '/tmp',
          hostTmux: null,
          appDefaultTmux: false,
        }),
      storage: storageMockState.storage!,
      ...options,
      worktreeDirectoryFileSystem: {
        mkdir: async (targetPath, mkdirOptions) => {
          try {
            fs.mkdirSync(targetPath, mkdirOptions);
            return ok();
          } catch (error) {
            return err({ message: error instanceof Error ? error.message : String(error) });
          }
        },
        realPath: async (targetPath) => {
          try {
            return ok(fs.realpathSync(targetPath));
          } catch (error) {
            return err({ message: error instanceof Error ? error.message : String(error) });
          }
        },
      },
    }
  );
}

vi.mock('./project-settings-storage', () => ({
  ProjectSettingsRepository: vi.fn(function ProjectSettingsRepository() {
    if (!storageMockState.storage) {
      throw new Error('ProjectSettingsRepository test storage was not configured');
    }
    return storageMockState.storage;
  }),
}));

vi.mock('electron', () => ({
  app: {
    getPath: vi.fn().mockReturnValue('/tmp'),
  },
}));

describe('ProjectSettingsProvider worktreeDirectory validation', () => {
  const tempDirs: string[] = [];
  const createStorage = (): ProjectSettingsStorage => {
    const rows = new Map<
      string,
      {
        baseProjectSettingsJson: string;
        shareableProjectSettingsJson: string;
        legacyConfigMigratedAt: string | null;
      }
    >();
    return {
      get: async (projectId) => rows.get(projectId),
      insertIfMissing: async (projectId, settings) => {
        if (!rows.has(projectId)) rows.set(projectId, settings);
      },
      update: async (projectId, settings) => {
        rows.set(projectId, { ...rows.get(projectId)!, ...settings });
      },
    };
  };

  beforeEach(() => {
    storageMockState.storage = createStorage();
  });

  afterEach(() => {
    storageMockState.storage = undefined;
    for (const dir of tempDirs.splice(0)) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });

  it('does not seed preserve patterns when the repo has no shared config', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);

    const provider = makeLocalProvider(projectPath);

    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('preservePatterns');
  });

  it('does not seed preserve patterns when shared config omits preservePatterns', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    fs.writeFileSync(
      path.join(projectPath, '.emdash.json'),
      JSON.stringify({ shellSetup: 'nvm use' })
    );

    const provider = makeLocalProvider(projectPath);

    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('preservePatterns');
  });

  it('does not seed preserve patterns when shared config defines preservePatterns', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    fs.writeFileSync(
      path.join(projectPath, '.emdash.json'),
      JSON.stringify({ preservePatterns: ['.env.shared'] })
    );

    const provider = makeLocalProvider(projectPath);

    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('preservePatterns');
  });

  it('exposes legacy DB preserve patterns only through the migration source', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const id = projectId();
    await storageMockState.storage!.insertIfMissing(id, {
      baseProjectSettingsJson: '{}',
      shareableProjectSettingsJson: JSON.stringify({ preservePatterns: [] }),
      legacyConfigMigratedAt: new Date().toISOString(),
    });
    const provider = makeLocalProvider(projectPath, undefined, id);

    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('preservePatterns');
    await expect(provider.readLegacyLifecycleSettings()).resolves.toEqual({
      preservePatterns: [],
    });
  });

  it('migrates shareable settings from a local-only root config', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    fs.writeFileSync(
      path.join(projectPath, '.emdash.json'),
      JSON.stringify({
        preservePatterns: ['.env.local'],
        shellSetup: 'nvm use',
        scripts: {
          setup: 'pnpm install',
          run: 'pnpm dev',
          teardown: 'pnpm cleanup',
        },
      })
    );

    const git = makeTrackingGit(false);
    const provider = makeLocalProvider(projectPath, { git });
    await provider.migrateAncientConfig();

    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('preservePatterns');
    await expect(provider.readLegacyLifecycleSettings()).resolves.toMatchObject({
      preservePatterns: ['.env.local'],
      scripts: {
        setup: 'pnpm install',
        run: 'pnpm dev',
        teardown: 'pnpm cleanup',
      },
    });
    // shellSetup was retired from project settings: stored/migrated values are inert.
    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('shellSetup');
    expect(git.isFileCleanlyTracked).toHaveBeenCalledWith(path.join(projectPath, '.emdash.json'));
  });

  it('keeps legacy lifecycle values hidden and retryable when host import fails', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const id = projectId();
    await storageMockState.storage!.insertIfMissing(id, {
      baseProjectSettingsJson: JSON.stringify({
        autoRunSetupScriptOnTaskCreation: false,
        autoRunRunScriptOnTaskCreation: true,
      }),
      shareableProjectSettingsJson: JSON.stringify({
        preservePatterns: [],
        scripts: { setup: 'legacy setup', run: 'legacy run' },
      }),
      legacyConfigMigratedAt: new Date().toISOString(),
    });
    const provider = makeLocalProvider(projectPath, undefined, id);
    const importLegacyLifecycleSettings = vi.fn(async () => ({
      success: false as const,
      error: { type: 'workspace-not-found' as const, workspaceId: 'repo-1' },
    }));
    const registry = {
      getProjectConfig: vi.fn(async () => ({
        success: true as const,
        data: { legacyDesktopSettingsMigrated: false },
      })),
      importLegacyLifecycleSettings,
    };

    await migrateProjectSettingsOnAttachment(
      { repositoryWorkspaceId: 'repo-1' },
      provider,
      registry as never
    );
    expect((await provider.patch({})).success).toBe(true);
    await expect(provider.getStoredGitSettings()).resolves.toEqual({});
    await expect(provider.readLegacyLifecycleSettings()).resolves.toEqual({
      preservePatterns: [],
      scripts: { setup: 'legacy setup', run: 'legacy run' },
      autoRunSetup: false,
      autoRunRun: true,
    });

    await migrateProjectSettingsOnAttachment(
      { repositoryWorkspaceId: 'repo-1' },
      provider,
      registry as never
    );
    expect(importLegacyLifecycleSettings).toHaveBeenCalledTimes(2);
    expect(importLegacyLifecycleSettings).toHaveBeenLastCalledWith({
      workspaceId: 'repo-1',
      settings: {
        preservePatterns: [],
        scripts: { setup: 'legacy setup', run: 'legacy run' },
        autoRunSetup: false,
        autoRunRun: true,
      },
    });
  });

  it('removes legacy lifecycle values after durable host import is confirmed', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const id = projectId();
    await storageMockState.storage!.insertIfMissing(id, {
      baseProjectSettingsJson: JSON.stringify({
        autoRunSetupScriptOnTaskCreation: false,
        autoRunRunScriptOnTaskCreation: true,
      }),
      shareableProjectSettingsJson: JSON.stringify({
        preservePatterns: [],
        scripts: { setup: 'legacy setup', run: 'legacy run' },
      }),
      legacyConfigMigratedAt: new Date().toISOString(),
    });
    const provider = makeLocalProvider(projectPath, undefined, id);

    await provider.finalizeLegacyLifecycleSettings();

    const normalized = await storageMockState.storage!.get(id);
    expect(JSON.parse(normalized!.baseProjectSettingsJson)).toEqual({ tmuxDefaultMigrated: true });
    expect(JSON.parse(normalized!.shareableProjectSettingsJson)).toEqual({});
    await expect(provider.getStoredGitSettings()).resolves.not.toMatchObject({
      scripts: expect.anything(),
      autoRunSetupScriptOnTaskCreation: expect.anything(),
      autoRunRunScriptOnTaskCreation: expect.anything(),
    });
    await expect(provider.readLegacyLifecycleSettings()).resolves.toEqual({});
  });

  it('does not persist preserve patterns through ordinary DB settings writes', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const row = {
      baseProjectSettingsJson: '{}',
      shareableProjectSettingsJson: '{}',
      legacyConfigMigratedAt: new Date().toISOString(),
    };
    const update = vi.fn(async (_projectId: string, settings: Partial<typeof row>) => {
      Object.assign(row, settings);
    });
    storageMockState.storage = {
      get: async () => row,
      insertIfMissing: vi.fn(),
      update,
    };
    const provider = makeLocalProvider(projectPath);
    await provider.finalizeLegacyLifecycleSettings();
    update.mockClear();

    const result = await provider.patch({});

    expect(result.success).toBe(true);
    expect(JSON.parse(row.shareableProjectSettingsJson)).toEqual({});
    expect(update).toHaveBeenCalledOnce();
    expect(update.mock.calls[0]?.[1]).toEqual({
      baseProjectSettingsJson: JSON.stringify({ tmuxDefaultMigrated: true }),
    });
  });

  it('migrates local-only shareable settings for rows already base-migrated', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    fs.writeFileSync(
      path.join(projectPath, '.emdash.json'),
      JSON.stringify({
        shellSetup: 'nvm use',
        scripts: {
          setup: 'pnpm install',
          run: 'pnpm dev',
        },
      })
    );
    const row = {
      baseProjectSettingsJson: JSON.stringify({ defaultBranch: 'main' }),
      shareableProjectSettingsJson: '{}',
      legacyConfigMigratedAt: new Date().toISOString(),
    };
    const settingsStorage: ProjectSettingsStorage = {
      get: async () => row,
      insertIfMissing: vi.fn(),
      update: async (_projectId, settings) => {
        Object.assign(row, settings);
      },
    };
    storageMockState.storage = settingsStorage;
    const git = makeTrackingGit(false);
    const provider = makeLocalProvider(projectPath, { git });
    await provider.migrateAncientConfig();

    await expect(provider.readLegacyLifecycleSettings()).resolves.toMatchObject({
      scripts: {
        setup: 'pnpm install',
        run: 'pnpm dev',
      },
    });
    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('shellSetup');
    expect(git.isFileCleanlyTracked).toHaveBeenCalledWith(path.join(projectPath, '.emdash.json'));

    const result = await provider.patch({});
    expect(result.success).toBe(true);
    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('shellSetup');
    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('scripts');
    await expect(provider.readLegacyLifecycleSettings()).resolves.toMatchObject({
      scripts: { setup: 'pnpm install', run: 'pnpm dev' },
    });
  });

  it('keeps cleanly tracked shareable settings file-backed', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    fs.writeFileSync(
      path.join(projectPath, '.emdash.json'),
      JSON.stringify({
        shellSetup: 'nvm use',
        scripts: {
          setup: 'pnpm install',
          run: 'pnpm dev',
        },
      })
    );

    const git = makeTrackingGit(true);
    const provider = makeLocalProvider(projectPath, { git });
    await provider.migrateAncientConfig();

    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('preservePatterns');
    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('shellSetup');
    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('scripts');
    expect(git.isFileCleanlyTracked).toHaveBeenCalledWith(path.join(projectPath, '.emdash.json'));
  });

  it('does not seed computed worktreeDirectory into project settings', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);

    const provider = makeLocalProvider(projectPath);

    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('worktreeRoot');
    await expect(provider.getPlacementContext()).resolves.toEqual({
      hostWorktreeRoot: '/tmp/emdash/worktrees',
      builtInWorktreeRoot: '/tmp/emdash/worktrees',
      homeDirectory: '/tmp',
      hostTmux: null,
      appDefaultTmux: false,
    });
  });

  it('migrates legacy remote setting to baseRemote', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const row = {
      baseProjectSettingsJson: JSON.stringify({ remote: 'upstream' }),
      shareableProjectSettingsJson: '{}',
      legacyConfigMigratedAt: null,
    };
    const settingsStorage: ProjectSettingsStorage = {
      get: async () => row,
      insertIfMissing: vi.fn(),
      update: async (_projectId, settings) => {
        Object.assign(row, settings);
      },
    };
    storageMockState.storage = settingsStorage;
    const provider = makeLocalProvider(projectPath);
    await provider.migrateAncientConfig();

    await expect(provider.getStoredGitSettings()).resolves.toMatchObject({
      baseRemote: 'upstream',
    });
    expect(JSON.parse(row.baseProjectSettingsJson)).toEqual({
      baseRemote: 'upstream',
      tmuxDefaultMigrated: true,
    });
  });

  it('keeps computed worktreeDirectory default separate from configured overrides', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const provider = makeLocalProvider(projectPath);
    const expectedOverridePath = path.resolve(projectPath, 'worktrees');
    const result = await provider.patch({
      placement: { stored: { worktreeRoot: expectedOverridePath } },
    });
    expect(result.success).toBe(true);

    const expectedOverride = fs.realpathSync(expectedOverridePath);
    await expect(provider.getStoredGitSettings()).resolves.toMatchObject({
      worktreeRoot: expectedOverride,
    });
    await expect(provider.getPlacementContext()).resolves.toMatchObject({
      hostWorktreeRoot: '/tmp/emdash/worktrees',
    });
  });

  it('stores the selected GitHub account as base project settings', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const provider = makeLocalProvider(projectPath);

    const result = await provider.patch({
      gitIdentity: {
        stored: { githubAccount: { kind: 'account', accountId: 'github.com:42' } },
      },
    });

    expect(result.success).toBe(true);
    await expect(provider.getStoredGitSettings()).resolves.toMatchObject({
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
    });
  });

  it('stores null GitHub account selection as an explicit project override', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const provider = makeLocalProvider(projectPath);

    const result = await provider.patch({
      gitIdentity: { stored: { githubAccount: { kind: 'none' } } },
    });

    expect(result.success).toBe(true);
    await expect(provider.getStoredGitSettings()).resolves.toMatchObject({
      githubAccount: { kind: 'none' },
    });
  });

  it('patches the selected GitHub account without replacing other base settings', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const row = {
      baseProjectSettingsJson: JSON.stringify({
        defaultBranch: 'develop',
        baseRemote: 'upstream',
        tmux: true,
      }),
      shareableProjectSettingsJson: JSON.stringify({
        preservePatterns: ['.env.local'],
      }),
      legacyConfigMigratedAt: new Date().toISOString(),
    };
    const settingsStorage: ProjectSettingsStorage = {
      get: async () => row,
      insertIfMissing: vi.fn(),
      update: async (_projectId, settings) => {
        Object.assign(row, settings);
      },
    };
    storageMockState.storage = settingsStorage;
    const provider = makeLocalProvider(projectPath);

    const result = await provider.patch({
      gitIdentity: {
        stored: { githubAccount: { kind: 'account', accountId: 'github.com:42' } },
      },
    });

    expect(result.success).toBe(true);
    // The patch write-back also lazily migrates the row to the stored model
    // (structured defaultBranch, githubAccount ref). Without repo facts the
    // baseRemote/defaultBranch values stay pinned rather than demoted.
    expect(JSON.parse(row.baseProjectSettingsJson)).toEqual({
      defaultBranch: { remote: null, branch: 'develop' },
      baseRemote: 'upstream',
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
      tmux: true,
      tmuxDefaultMigrated: true,
    });
    await expect(provider.getStoredGitSettings()).resolves.toMatchObject({
      defaultBranch: { remote: null, branch: 'develop' },
      baseRemote: 'upstream',
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
    });
    await expect(provider.getStoredPlacementSettings()).resolves.toEqual({ tmux: true });
    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('preservePatterns');
  });

  it('retries legacy config migration after a failed attempt', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const row = {
      baseProjectSettingsJson: '{}',
      shareableProjectSettingsJson: '{}',
      legacyConfigMigratedAt: null,
    };
    let updateAttempts = 0;
    const settingsStorage: ProjectSettingsStorage = {
      get: async () => row,
      insertIfMissing: vi.fn(),
      update: async (_projectId, settings) => {
        updateAttempts += 1;
        if (updateAttempts === 1) throw new Error('db write failed');
        Object.assign(row, settings);
      },
    };
    storageMockState.storage = settingsStorage;
    const provider = makeLocalProvider(projectPath);

    await expect(provider.migrateAncientConfig()).rejects.toThrow('db write failed');
    await expect(provider.migrateAncientConfig()).resolves.toBeUndefined();
    await expect(provider.migrateAncientConfig()).resolves.toBeUndefined();

    expect(updateAttempts).toBe(2);
  });

  it('patches DB settings without mutating legacy shareable settings', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const row = {
      baseProjectSettingsJson: JSON.stringify({
        worktreeDirectory: path.join(projectPath, 'not-yet-created'),
      }),
      shareableProjectSettingsJson: JSON.stringify({
        preservePatterns: ['.env'],
        scripts: {
          setup: 'pnpm install',
          run: 'pnpm dev',
        },
      }),
      legacyConfigMigratedAt: new Date().toISOString(),
    };
    const settingsStorage: ProjectSettingsStorage = {
      get: async () => row,
      insertIfMissing: vi.fn(),
      update: async (_projectId, settings) => {
        Object.assign(row, settings);
      },
    };
    storageMockState.storage = settingsStorage;
    const provider = makeLocalProvider(projectPath);

    const result = await provider.patch({
      gitIdentity: {
        stored: { githubAccount: { kind: 'account', accountId: 'github.com:42' } },
      },
    });

    expect(result.success).toBe(true);
    expect(JSON.parse(row.shareableProjectSettingsJson)).toEqual({
      preservePatterns: ['.env'],
      scripts: {
        setup: 'pnpm install',
        run: 'pnpm dev',
      },
    });
    expect(JSON.parse(row.baseProjectSettingsJson)).toMatchObject({
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
    });
  });

  it('normalizes and canonicalizes local absolute worktreeDirectory on update', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);

    const provider = makeLocalProvider(projectPath);
    const expectedPath = path.resolve(projectPath, 'worktrees');
    const result = await provider.patch({
      placement: { stored: { worktreeRoot: expectedPath } },
    });
    expect(result.success).toBe(true);

    expect(fs.existsSync(expectedPath)).toBe(true);

    await expect(provider.getStoredGitSettings()).resolves.toMatchObject({
      worktreeRoot: fs.realpathSync(expectedPath),
    });
  });

  it('patches and resets stored DB domains without touching lifecycle config', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    const worktreeRoot = path.join(projectPath, 'worktrees');
    const provider = makeLocalProvider(projectPath);

    await expect(
      provider.patch({
        gitIdentity: {
          stored: {
            baseRemote: 'origin',
            githubAccount: { kind: 'none' },
            agentGitCredentials: 'none',
          },
        },
        placement: {
          stored: { worktreeRoot, tmux: true },
        },
      })
    ).resolves.toEqual({ success: true, data: undefined });
    await expect(provider.getStoredGitSettings()).resolves.toMatchObject({
      baseRemote: 'origin',
      githubAccount: { kind: 'none' },
      agentGitCredentials: 'none',
      worktreeRoot: fs.realpathSync(worktreeRoot),
    });
    await expect(provider.getStoredPlacementSettings()).resolves.toEqual({ tmux: true });

    await expect(
      provider.patch({
        gitIdentity: {
          stored: {
            baseRemote: null,
            githubAccount: null,
            agentGitCredentials: null,
          },
        },
        placement: {
          stored: { worktreeRoot: null, tmux: null },
        },
      })
    ).resolves.toEqual({ success: true, data: undefined });
    await expect(provider.getStoredGitSettings()).resolves.toEqual({});
    await expect(provider.getStoredPlacementSettings()).resolves.toEqual({});
    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty(
      'agentGitCredentials'
    );
  });

  it('rejects local relative worktreeDirectory values', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);

    const provider = makeLocalProvider(projectPath);
    const result = await provider.patch({
      placement: { stored: { worktreeRoot: 'worktrees' } },
    });

    expect(result).toEqual({
      success: false,
      error: { type: 'invalid-worktree-directory' },
    });
  });

  it('rejects foreign absolute worktreeDirectory values for local projects', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);

    const provider = makeLocalProvider(projectPath);
    const foreignPath = process.platform === 'win32' ? '/tmp/worktrees' : 'C:\\worktrees';
    const result = await provider.patch({
      placement: { stored: { worktreeRoot: foreignPath } },
    });

    expect(result).toEqual({
      success: false,
      error: { type: 'invalid-worktree-directory' },
    });
  });

  it('surfaces local worktreeDirectory validation errors', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);
    fs.writeFileSync(path.join(projectPath, 'not-a-directory'), 'file');

    const provider = makeLocalProvider(projectPath);
    const result = await provider.patch({
      placement: {
        stored: { worktreeRoot: path.join(projectPath, 'not-a-directory', 'worktrees') },
      },
    });
    expect(result).toEqual({
      success: false,
      error: { type: 'invalid-worktree-directory' },
    });
  });

  it('clears blank local worktreeDirectory values', async () => {
    const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-settings-local-'));
    tempDirs.push(projectPath);

    const provider = makeLocalProvider(projectPath);
    const result = await provider.patch({
      placement: { stored: { worktreeRoot: '   ' } },
    });
    expect(result.success).toBe(true);

    await expect(provider.getStoredGitSettings()).resolves.not.toHaveProperty('worktreeRoot');
  });
});
