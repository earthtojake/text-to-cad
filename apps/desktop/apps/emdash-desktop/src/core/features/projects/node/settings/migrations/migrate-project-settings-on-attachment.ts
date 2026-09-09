import { log } from '@emdash/shared/logger';
import type { Project } from '@core/primitives/projects/api';
import type { WorkspaceRegistryRuntimeClient } from '@core/services/runtime-broker/api/clients';
import type { ProjectSettingsMigrationReader } from './migration-reader';

export type ProjectSettingsAttachmentMigrationOptions = {
  migrateAppWorktreeRoot?: () => Promise<void>;
};

export async function migrateProjectSettingsOnAttachment(
  project: Pick<Project, 'repositoryWorkspaceId'>,
  settings: ProjectSettingsMigrationReader,
  workspaceRegistry: Pick<
    WorkspaceRegistryRuntimeClient,
    'getProjectConfig' | 'importLegacyLifecycleSettings'
  >,
  options: ProjectSettingsAttachmentMigrationOptions = {}
): Promise<void> {
  if (options.migrateAppWorktreeRoot) {
    try {
      await options.migrateAppWorktreeRoot();
    } catch (error) {
      log.warn('App worktree-root migration failed; retrying on next Project attachment', {
        error,
      });
    }
  }
  await settings.migrateAncientConfig();

  try {
    const legacy = await settings.readLegacyLifecycleSettings();
    if (!project.repositoryWorkspaceId) return;
    const current = await workspaceRegistry.getProjectConfig({
      workspaceId: project.repositoryWorkspaceId,
    });
    if (!current.success) return;
    if (current.data.legacyDesktopSettingsMigrated) {
      await settings.finalizeLegacyLifecycleSettings();
      return;
    }

    const migrated = await workspaceRegistry.importLegacyLifecycleSettings({
      workspaceId: project.repositoryWorkspaceId,
      settings: {
        ...(legacy.preservePatterns !== undefined
          ? { preservePatterns: legacy.preservePatterns }
          : {}),
        ...(legacy.scripts ? { scripts: legacy.scripts } : {}),
        ...(legacy.autoRunSetup !== undefined ? { autoRunSetup: legacy.autoRunSetup } : {}),
        ...(legacy.autoRunRun !== undefined ? { autoRunRun: legacy.autoRunRun } : {}),
      },
    });
    if (!migrated.success) {
      log.warn(
        'Host rejected the lifecycle settings migration; retrying on next Project attachment',
        { error: migrated.error }
      );
      return;
    }
    if (!migrated.data.legacyDesktopSettingsMigrated) {
      log.warn(
        'Host did not confirm the lifecycle settings migration; retrying on next Project attachment'
      );
      return;
    }
    await settings.finalizeLegacyLifecycleSettings();
  } catch (error) {
    // Attachment remains available; the absent completion marker retries on the next allocation.
    log.warn('Lifecycle settings migration failed; retrying on next Project attachment', {
      error,
    });
  }
}
