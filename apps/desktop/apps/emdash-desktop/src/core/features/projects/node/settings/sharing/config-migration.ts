import type { PatchPersonalProjectConfigInput } from '@emdash/core/runtimes/workspace-registry/api';
import type { Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import type {
  MigrateProjectConfigRequest,
  ProjectConfigMigration,
  ShareableProjectSettingsWriteField,
} from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import {
  fileKey,
  fsErrorMessage,
  type FilesClientScope,
} from '@core/services/runtime-broker/node/files';
import { codexConfigMigrator } from './codex-config-migration';
import { conductorConfigMigrator } from './conductor-config-migration';
import { errorMessage, projectPath, writeConfigFailed } from './config-migration-utils';
import { paseoConfigMigrator } from './paseo-config-migration';
import { supersetConfigMigrator } from './superset-config-migration';
import { CONFIG_FILE } from './workspace-config-file';

export type ProjectConfigMigrationWriter = {
  patchPersonalConfig(
    patch: PatchPersonalProjectConfigInput['patch']
  ): Promise<Result<void, UpdateProjectSettingsError>>;
  clearPersonalFields(
    fields: ShareableProjectSettingsWriteField[]
  ): Promise<Result<void, UpdateProjectSettingsError>>;
};

export type ProjectConfigMigrator = {
  provider: ProjectConfigMigration['provider'];
  inspect: (
    project: ProjectProvider,
    files: FilesClientScope
  ) => Promise<ProjectConfigMigration | null>;
  migrate: (
    project: ProjectProvider,
    request: MigrateProjectConfigRequest,
    writer: ProjectConfigMigrationWriter
  ) => Promise<Result<ProjectConfigMigration, UpdateProjectSettingsError>>;
};

const PROJECT_CONFIG_MIGRATORS = [
  conductorConfigMigrator,
  supersetConfigMigrator,
  paseoConfigMigrator,
  codexConfigMigrator,
] as const;

function projectConfigPath(project: ProjectProvider): string {
  return projectPath(project, CONFIG_FILE);
}

export async function inspectProjectConfigMigrations(
  project: ProjectProvider
): Promise<ProjectConfigMigration[]> {
  const configPath = projectConfigPath(project);
  const existingConfig = await project.files.client.fs.exists(fileKey(project.files, configPath));
  if (!existingConfig.success) {
    log.warn(`Failed to inspect ${CONFIG_FILE} before config migration`, existingConfig.error);
    return [];
  }
  if (existingConfig.data.exists) return [];

  const migrations = await Promise.all(
    PROJECT_CONFIG_MIGRATORS.map(async (migrator) => {
      try {
        return await migrator.inspect(project, project.files);
      } catch (error) {
        log.warn(`Failed to inspect ${migrator.provider} config for migration`, { error });
        return null;
      }
    })
  );

  return migrations.filter((migration): migration is ProjectConfigMigration => migration !== null);
}

export async function migrateProjectConfigFromProvider(
  project: ProjectProvider,
  request: MigrateProjectConfigRequest,
  writer: ProjectConfigMigrationWriter
): Promise<Result<ProjectConfigMigration, UpdateProjectSettingsError>> {
  try {
    const configPath = projectConfigPath(project);
    const existingConfig = await project.files.client.fs.exists(fileKey(project.files, configPath));
    if (!existingConfig.success) {
      return writeConfigFailed(
        `Could not check existing ${CONFIG_FILE}: ${fsErrorMessage(existingConfig.error)}`
      );
    }
    if (existingConfig.data.exists) {
      return writeConfigFailed(`${CONFIG_FILE} already exists.`);
    }

    const migrator = PROJECT_CONFIG_MIGRATORS.find(
      (candidate) => candidate.provider === request.provider
    );
    if (!migrator) return writeConfigFailed('Unsupported config provider.');

    return await migrator.migrate(project, request, writer);
  } catch (error) {
    log.warn(`Failed to migrate ${request.provider} config to project config`, { error });
    return writeConfigFailed(errorMessage(error));
  }
}
