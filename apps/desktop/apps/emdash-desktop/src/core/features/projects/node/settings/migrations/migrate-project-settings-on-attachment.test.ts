import { describe, expect, it, vi } from 'vitest';
import { migrateProjectSettingsOnAttachment } from './migrate-project-settings-on-attachment';

function hostState(migrated: boolean) {
  return {
    success: true as const,
    data: {
      legacyDesktopSettingsMigrated: migrated,
    },
  };
}

describe('migrateProjectSettingsOnAttachment', () => {
  it('orders every migration, retries failed imports, and becomes idempotent after confirmation', async () => {
    const events: string[] = [];
    let hostMigrated = false;
    let importAttempts = 0;
    const migrationReader = {
      migrateAncientConfig: vi.fn(async () => {
        events.push('ancient');
      }),
      readLegacyLifecycleSettings: vi.fn(async () => {
        events.push('normalize-and-read');
        return {
          preservePatterns: [],
          scripts: { setup: 'pnpm install', run: 'pnpm dev' },
          autoRunSetup: false,
          autoRunRun: false,
        };
      }),
      finalizeLegacyLifecycleSettings: vi.fn(async () => {
        events.push('finalize');
      }),
    };
    const workspaceRegistry = {
      getProjectConfig: vi.fn(async () => {
        events.push('marker');
        return hostState(hostMigrated);
      }),
      importLegacyLifecycleSettings: vi.fn(async () => {
        events.push('import');
        importAttempts += 1;
        if (importAttempts === 1) {
          return {
            success: false as const,
            error: { type: 'workspace-not-found' as const, workspaceId: 'repo-1' },
          };
        }
        hostMigrated = true;
        return hostState(true);
      }),
    };
    const project = { repositoryWorkspaceId: 'repo-1' };
    const options = {
      migrateAppWorktreeRoot: vi.fn(async () => {
        events.push('app-worktree-root');
      }),
    };

    await migrateProjectSettingsOnAttachment(
      project,
      migrationReader,
      workspaceRegistry as never,
      options
    );

    expect(events).toEqual([
      'app-worktree-root',
      'ancient',
      'normalize-and-read',
      'marker',
      'import',
    ]);
    expect(migrationReader.finalizeLegacyLifecycleSettings).not.toHaveBeenCalled();

    events.length = 0;
    await migrateProjectSettingsOnAttachment(
      project,
      migrationReader,
      workspaceRegistry as never,
      options
    );

    expect(events).toEqual([
      'app-worktree-root',
      'ancient',
      'normalize-and-read',
      'marker',
      'import',
      'finalize',
    ]);
    expect(workspaceRegistry.importLegacyLifecycleSettings).toHaveBeenLastCalledWith({
      workspaceId: 'repo-1',
      settings: {
        preservePatterns: [],
        scripts: { setup: 'pnpm install', run: 'pnpm dev' },
        autoRunSetup: false,
        autoRunRun: false,
      },
    });

    events.length = 0;
    await migrateProjectSettingsOnAttachment(
      project,
      migrationReader,
      workspaceRegistry as never,
      options
    );

    expect(events).toEqual([
      'app-worktree-root',
      'ancient',
      'normalize-and-read',
      'marker',
      'finalize',
    ]);
    expect(migrationReader.readLegacyLifecycleSettings).toHaveBeenCalledTimes(3);
    expect(workspaceRegistry.importLegacyLifecycleSettings).toHaveBeenCalledTimes(2);
    expect(migrationReader.finalizeLegacyLifecycleSettings).toHaveBeenCalledTimes(2);
    expect(migrationReader.migrateAncientConfig).toHaveBeenCalledTimes(3);
    expect(options.migrateAppWorktreeRoot).toHaveBeenCalledTimes(3);
  });

  it('keeps legacy settings when the Host does not confirm the migration', async () => {
    const migrationReader = {
      migrateAncientConfig: vi.fn(async () => {}),
      readLegacyLifecycleSettings: vi.fn(async () => ({ scripts: { setup: 'pnpm install' } })),
      finalizeLegacyLifecycleSettings: vi.fn(async () => {}),
    };
    const workspaceRegistry = {
      getProjectConfig: vi.fn(async () => hostState(false)),
      importLegacyLifecycleSettings: vi.fn(async () => hostState(false)),
    };

    await migrateProjectSettingsOnAttachment(
      { repositoryWorkspaceId: 'repo-1' },
      migrationReader,
      workspaceRegistry as never
    );

    expect(workspaceRegistry.importLegacyLifecycleSettings).toHaveBeenCalledOnce();
    expect(migrationReader.finalizeLegacyLifecycleSettings).not.toHaveBeenCalled();
  });
});
