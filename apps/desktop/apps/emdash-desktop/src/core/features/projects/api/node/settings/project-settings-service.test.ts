import { err, ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectSettingsService } from './project-settings-service';

const sharingMocks = vi.hoisted(() => ({
  resolveTarget: vi.fn(async () => ({
    type: 'project' as const,
    label: 'Project repository',
    path: '/repo',
    configPath: '/repo/.emdash.json',
    sourceWorkspaceId: 'repo-1',
    files: {},
  })),
  write: vi.fn(async () => ({ success: true as const, data: ['scripts.setup'] as const })),
}));

vi.mock('../../../node/settings/sharing/project-settings-target-resolver', () => ({
  resolveAllProjectSettingsTargets: vi.fn(async () => [
    {
      type: 'project',
      label: 'Project repository',
      path: '/repo',
      configPath: '/repo/.emdash.json',
      files: {},
    },
  ]),
  getProjectSettingsWriteTargets: vi.fn((targets) =>
    targets.map(({ files: _files, ...target }: { files: unknown }) => target)
  ),
  resolveProjectSettingsTarget: sharingMocks.resolveTarget,
}));

vi.mock('../../../node/settings/sharing/share-project-settings-to-config', () => ({
  shareProjectSettingsToConfig: sharingMocks.write,
}));

function configState() {
  return {
    workspaceId: 'repo-1',
    repositoryId: 'repo-1',
    resolved: {
      preservePatterns: { value: [], from: 'built-in' as const },
      setup: { value: 'old setup', from: 'personal' as const },
      autoRunSetup: { value: true, from: 'built-in' as const },
      autoRunRun: { value: true, from: 'personal' as const },
    },
    personalConfig: { scripts: { setup: 'old setup' }, autoRunRun: true },
    sources: {
      preservePatterns: [],
      prepare: [],
      setup: [
        {
          workspaceId: 'repo-1',
          path: '/repo/.emdash.json',
          value: 'team setup',
        },
      ],
      run: [],
      teardown: [],
      shellSetup: [],
    },
    legacyDesktopSettingsMigrated: true,
  };
}

function fixture() {
  const patch = vi.fn(async () => ok(undefined));
  const hostPatch = vi.fn(async () => ok(undefined));
  const patchPersonalProjectConfig = vi.fn(async () => ok(configState()));
  const refreshProjectConfig = vi.fn(async () => ok(configState()));
  const getProjectConfig = vi.fn(async () => ok(configState()));
  const createWorkspace = vi.fn(async () => ok({} as never));
  const configSource = {};
  const projectConfigState = vi.fn(() => ({
    asLiveSource: () => configSource,
  }));
  const project = {
    projectId: 'project-1',
    repoPath: '/repo',
    project: {
      type: 'local' as const,
      id: 'project-1',
      name: 'Project',
      path: '/repo',
      baseRef: 'main',
      repositoryWorkspaceId: 'repo-1',
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    },
    settings: {
      patch: hostPatch,
      getStoredGitSettings: vi.fn(async () => ({
        baseRemote: 'origin',
        pushRemote: 'stale-fork',
        agentGitCredentials: 'none' as const,
        worktreeRoot: '/project/worktrees',
      })),
      getStoredPlacementSettings: vi.fn(async () => ({ tmux: true })),
      getPlacementContext: vi.fn(async () => ({
        hostWorktreeRoot: null,
        builtInWorktreeRoot: '/tmp/worktrees',
        homeDirectory: '/tmp',
        hostTmux: false,
        appDefaultTmux: true,
      })),
    },
    workspaceRegistry: {
      getProjectConfig,
      createWorkspace,
      patchPersonalProjectConfig,
      refreshProjectConfig,
      projectConfig: { state: projectConfigState },
    },
  };
  const readDurable = vi.fn(async () =>
    ok({
      gitIdentity: {
        stored: {
          baseRemote: 'origin',
          pushRemote: 'stale-fork',
          agentGitCredentials: 'none' as const,
        },
      },
      placement: {
        stored: { worktreeRoot: '/project/worktrees', tmux: true },
      },
    })
  );
  const service = new ProjectSettingsService({
    db: {} as never,
    projects: { requireAttached: () => ok(project as never) },
    workspaceIdentity: {} as never,
    loadProject: async () => project.project,
    durableSettings: {
      read: readDurable,
      patch,
    },
  });
  return {
    service,
    patch,
    hostPatch,
    readDurable,
    patchPersonalProjectConfig,
    refreshProjectConfig,
    getProjectConfig,
    createWorkspace,
    projectConfigState,
    configSource,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  sharingMocks.write.mockResolvedValue({ success: true, data: ['scripts.setup'] });
});

describe('ProjectSettingsService personal lifecycle writes', () => {
  it('forwards the project config live source by repository workspace id', async () => {
    const { service, projectConfigState, configSource } = fixture();

    await expect(service.getProjectConfigLiveSource('project-1')).resolves.toBe(configSource);
    expect(projectConfigState).toHaveBeenCalledWith({ workspaceId: 'repo-1' }, 'current');
  });

  it('returns self-contained raw, resolved, source, and write-target snapshots', async () => {
    const { service } = fixture();

    const result = await service.getProjectSettingsPage('project-1');

    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.host.kind).toBe('observed');
    if (result.data.host.kind !== 'observed') return;
    const domains = {
      ...result.data.host.value.domains,
      ...result.data.durable,
      placement: {
        ...result.data.host.value.domains.placement,
        ...result.data.durable.placement,
      },
    };
    expect(domains.lifecycle).toMatchObject({
      personal: { scripts: { setup: 'old setup' }, autoRunRun: true },
      team: { scripts: { setup: 'team setup' } },
      resolved: {
        setup: { value: 'old setup', from: 'personal' },
      },
      sources: {
        setup: [
          {
            label: 'Project repository',
            path: '/repo',
            configPath: '/repo/.emdash.json',
            value: 'team setup',
          },
        ],
      },
      writeTargets: [
        {
          type: 'project',
          label: 'Project repository',
          path: '/repo',
          configPath: '/repo/.emdash.json',
        },
      ],
    });
    expect(domains.gitIdentity).toEqual({
      stored: {
        baseRemote: 'origin',
        pushRemote: 'stale-fork',
        agentGitCredentials: 'none',
      },
    });
    expect(domains.placement).toMatchObject({
      stored: { worktreeRoot: '/project/worktrees', tmux: true },
      layers: {
        hostWorktreeRoot: null,
        builtInWorktreeRoot: '/tmp/worktrees',
        homeDirectory: '/tmp',
        hostTmux: false,
        appDefaultTmux: true,
      },
      resolved: {
        worktreeRoot: {
          value: '/project/worktrees',
          provenance: { kind: 'set' },
        },
        tmux: {
          value: true,
          provenance: { kind: 'set' },
        },
      },
    });
  });

  it('does not recreate an unknown Host identity while assembling settings', async () => {
    const { service, getProjectConfig, createWorkspace } = fixture();
    getProjectConfig.mockResolvedValue(
      err({ type: 'workspace-not-found', workspaceId: 'repo-1' }) as never
    );

    const result = await service.getProjectSettingsPage('project-1');

    expect(result).toEqual({ success: false, error: { type: 'error' } });
    expect(createWorkspace).not.toHaveBeenCalled();
    expect(getProjectConfig).toHaveBeenCalledOnce();
  });

  it('returns unresolved registry failures from page, share, and migration operations', async () => {
    const operations = [
      (service: ProjectSettingsService) => service.getProjectSettingsPage('project-1'),
      (service: ProjectSettingsService) =>
        service.shareProjectSettingsToConfig('project-1', {
          target: { type: 'project' },
          fields: ['scripts.setup'],
        }),
      (service: ProjectSettingsService) =>
        service.migrateProjectConfig('project-1', {
          providerId: 'codex',
        } as never),
    ];

    for (const operation of operations) {
      const { service, getProjectConfig, createWorkspace } = fixture();
      getProjectConfig.mockResolvedValue(
        err({ type: 'workspace-not-found', workspaceId: 'repo-1' }) as never
      );
      createWorkspace.mockResolvedValue(err({ type: 'path-not-found', path: '/repo' }) as never);

      await expect(operation(service)).resolves.toEqual({
        success: false,
        error: { type: 'error' },
      });
    }
  });

  it('applies ordinary saves as explicit registry and DB domain patches', async () => {
    const { service, patch, hostPatch, patchPersonalProjectConfig } = fixture();

    const result = await service.updateProjectSettings('project-1', {
      lifecycle: {
        personal: {
          scripts: { setup: 'new setup', run: null },
          autoRunRun: null,
        },
      },
      fileHandling: {
        personal: { preservePatterns: ['personal/**'] },
      },
      gitIdentity: {
        stored: { baseRemote: 'origin', agentGitCredentials: 'none' },
      },
      placement: {
        stored: { worktreeRoot: '/tmp/worktrees', tmux: true },
      },
    });

    expect(result.success).toBe(true);
    expect(patchPersonalProjectConfig).toHaveBeenCalledWith({
      workspaceId: 'repo-1',
      patch: {
        scripts: { setup: 'new setup', run: null },
        autoRunRun: null,
        preservePatterns: ['personal/**'],
      },
    });
    expect(patch).toHaveBeenCalledWith('project-1', {
      gitIdentity: {
        stored: { baseRemote: 'origin', agentGitCredentials: 'none' },
      },
      placement: { stored: { tmux: true } },
    });
    expect(hostPatch).toHaveBeenCalledWith({
      placement: { stored: { worktreeRoot: '/tmp/worktrees' } },
    });
  });

  it('reset removes only the requested personal fields', async () => {
    const { service, patchPersonalProjectConfig } = fixture();

    const result = await service.updateProjectSettings('project-1', {
      lifecycle: {
        personal: { scripts: { setup: null }, autoRunRun: null },
      },
      fileHandling: {
        personal: { preservePatterns: null },
      },
    });

    expect(result.success).toBe(true);
    expect(patchPersonalProjectConfig).toHaveBeenCalledWith({
      workspaceId: 'repo-1',
      patch: {
        scripts: { setup: null },
        autoRunRun: null,
        preservePatterns: null,
      },
    });
  });
});

describe('ProjectSettingsService sharing orchestration', () => {
  it('writes, refreshes, then clears exactly the fields that were written', async () => {
    const { service, refreshProjectConfig, patchPersonalProjectConfig } = fixture();

    const result = await service.shareProjectSettingsToConfig('project-1', {
      target: { type: 'project' },
      fields: ['scripts.setup', 'scripts.run'],
    });

    expect(result.success).toBe(true);
    expect(sharingMocks.write).toHaveBeenCalledWith(
      expect.objectContaining({ configPath: '/repo/.emdash.json' }),
      ['scripts.setup', 'scripts.run'],
      configState().personalConfig
    );
    expect(refreshProjectConfig).toHaveBeenCalledWith({ workspaceId: 'repo-1' });
    expect(patchPersonalProjectConfig).toHaveBeenCalledWith({
      workspaceId: 'repo-1',
      patch: { scripts: { setup: null } },
    });
    expect(sharingMocks.write.mock.invocationCallOrder[0]).toBeLessThan(
      refreshProjectConfig.mock.invocationCallOrder[0] ?? 0
    );
    expect(refreshProjectConfig.mock.invocationCallOrder[0]).toBeLessThan(
      patchPersonalProjectConfig.mock.invocationCallOrder[0] ?? 0
    );
  });

  it('does not clear personal fields if the consistency refresh fails', async () => {
    const { service, refreshProjectConfig, patchPersonalProjectConfig } = fixture();
    refreshProjectConfig.mockResolvedValueOnce({
      success: false,
      error: { type: 'error' },
    } as never);

    const result = await service.shareProjectSettingsToConfig('project-1', {
      target: { type: 'project' },
      fields: ['scripts.setup'],
    });

    expect(result).toEqual({
      success: false,
      error: {
        type: 'write-config-failed',
        message:
          'Wrote .emdash.json, but failed to refresh shared project settings. Personal settings were not cleared.',
      },
    });
    expect(patchPersonalProjectConfig).not.toHaveBeenCalled();
  });
});

describe('ProjectSettingsService offline authority boundaries', () => {
  it('loads durable settings while effective attachment is unavailable', async () => {
    const unavailable = {
      type: 'host-unavailable' as const,
      host: { type: 'remote' as const, id: 'ssh-private-id' },
      reason: 'offline' as const,
      message: 'Host is offline',
    };
    const loadProject = vi.fn(async () => ({
      type: 'ssh' as const,
      id: 'project-1',
      name: 'Project',
      path: '/repo',
      baseRef: 'main',
      connectionId: 'ssh-private-id',
      repositoryWorkspaceId: 'repo-1',
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    }));
    const readDurable = vi.fn(async () =>
      ok({
        gitIdentity: {
          stored: {
            baseRemote: 'origin',
            githubAccount: { kind: 'none' as const },
          },
        },
        placement: { stored: { tmux: true } },
      })
    );
    const requireAttached = vi.fn(() => err(unavailable));
    const service = new ProjectSettingsService({
      db: {} as never,
      projects: { requireAttached },
      workspaceIdentity: {} as never,
      loadProject,
      durableSettings: {
        read: readDurable,
        patch: vi.fn(),
      },
    } as never);

    await expect(service.getProjectSettingsPage('project-1')).resolves.toEqual(
      ok({
        durable: {
          gitIdentity: {
            stored: {
              baseRemote: 'origin',
              githubAccount: { kind: 'none' },
            },
          },
          placement: { stored: { tmux: true } },
        },
        host: { kind: 'never-observed' },
      })
    );
    expect(loadProject).toHaveBeenCalledWith('project-1');
    expect(readDurable).toHaveBeenCalledWith('project-1');
    expect(requireAttached).toHaveBeenCalledWith('project-1');
  });

  it('preserves the typed attachment race for Host-backed writes', async () => {
    const unavailable = {
      type: 'attachment-unavailable' as const,
      host: { type: 'local' as const },
      phase: 'waiting' as const,
    };
    const service = new ProjectSettingsService({
      db: {} as never,
      projects: { requireAttached: vi.fn(() => err(unavailable)) },
      workspaceIdentity: {} as never,
      loadProject: vi.fn(async () => ({
        type: 'local',
        id: 'project-1',
        name: 'Project',
        path: '/repo',
        baseRef: 'main',
        repositoryWorkspaceId: 'repo-1',
        createdAt: '2026-08-13T00:00:00.000Z',
        updatedAt: '2026-08-13T00:00:00.000Z',
      })),
      durableSettings: {
        read: vi.fn(async () =>
          ok({
            gitIdentity: { stored: {} },
            placement: { stored: {} },
          })
        ),
        patch: vi.fn(async () => ok()),
      },
    } as never);

    await expect(
      service.shareProjectSettingsToConfig('project-1', {
        target: { type: 'project' },
        fields: ['scripts.setup'],
      })
    ).resolves.toEqual(err(unavailable));
  });
});
