import type { Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import z from 'zod';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import {
  type MigrateProjectConfigRequest,
  type ProjectConfigMigration,
  type ShareableProjectSettings,
  type ShareableProjectSettingsWriteField,
} from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import { fileKey, type FilesClientScope } from '@core/services/runtime-broker/node/files';
import { parseJsonObject } from '../project-settings-json';
import type { ProjectConfigMigrationWriter, ProjectConfigMigrator } from './config-migration';
import {
  addScript,
  applyProjectConfigMigration,
  errorMessage,
  projectPath,
  trimmedText,
  writeConfigFailed,
} from './config-migration-utils';

const CONDUCTOR_CONFIG_FILE = 'conductor.json';
const CONDUCTOR_WORKTREE_INCLUDE_FILE = '.worktreeinclude';

const conductorConfigSchema = z
  .object({
    scripts: z
      .object({
        setup: z.string().optional(),
        run: z.string().optional(),
        archive: z.string().optional(),
      })
      .optional(),
    runScriptMode: z.enum(['concurrent', 'nonconcurrent']).optional(),
    enterpriseDataPrivacy: z.boolean().optional(),
  })
  .passthrough();

type ConductorMigrationData = {
  settings: ShareableProjectSettings;
  files: string[];
  fields: ShareableProjectSettingsWriteField[];
  unsupportedFields: string[];
};

function parseWorktreeInclude(content: string): string[] {
  return content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'));
}

function toConductorMigration(data: ConductorMigrationData): ProjectConfigMigration | null {
  if (data.fields.length === 0) return null;
  return {
    provider: 'conductor',
    label: 'Conductor',
    files: data.files,
    fields: data.fields,
    unsupportedFields: data.unsupportedFields,
  };
}

async function readConductorMigrationData(
  project: ProjectProvider,
  files: FilesClientScope
): Promise<ConductorMigrationData> {
  const data: ConductorMigrationData = {
    settings: {},
    files: [],
    fields: [],
    unsupportedFields: [],
  };

  const conductorConfigPath = projectPath(project, CONDUCTOR_CONFIG_FILE);
  const hasConductorConfig = await files.client.fs.exists(fileKey(files, conductorConfigPath));
  if (!hasConductorConfig.success) {
    log.warn('Failed to inspect Conductor config for migration', hasConductorConfig.error);
  }
  if (hasConductorConfig.success && hasConductorConfig.data.exists) {
    const content = await files.client.fs.readText(fileKey(files, conductorConfigPath));
    if (!content.success) {
      log.warn('Failed to read Conductor config for migration', content.error);
    } else if (content.data.truncated) {
      log.warn('Conductor config was truncated during migration', {
        path: conductorConfigPath,
        totalSize: content.data.totalSize,
      });
    } else {
      const conductorConfig = conductorConfigSchema.parse(parseJsonObject(content.data.content));
      data.files.push(CONDUCTOR_CONFIG_FILE);

      const setup = trimmedText(conductorConfig.scripts?.setup);
      const run = trimmedText(conductorConfig.scripts?.run);
      const archive = trimmedText(conductorConfig.scripts?.archive);

      addScript(data, 'scripts.setup', setup);
      addScript(data, 'scripts.run', run);
      addScript(data, 'scripts.teardown', archive);

      if (conductorConfig.runScriptMode !== undefined) data.unsupportedFields.push('runScriptMode');
      if (conductorConfig.enterpriseDataPrivacy !== undefined) {
        data.unsupportedFields.push('enterpriseDataPrivacy');
      }
    }
  }

  const worktreeIncludePath = projectPath(project, CONDUCTOR_WORKTREE_INCLUDE_FILE);
  const hasWorktreeInclude = await files.client.fs.exists(fileKey(files, worktreeIncludePath));
  if (!hasWorktreeInclude.success) {
    log.warn(
      'Failed to inspect Conductor worktree include for migration',
      hasWorktreeInclude.error
    );
  }
  if (hasWorktreeInclude.success && hasWorktreeInclude.data.exists) {
    const content = await files.client.fs.readText(fileKey(files, worktreeIncludePath));
    if (!content.success) {
      log.warn('Failed to read Conductor worktree include for migration', content.error);
      return data;
    }
    if (content.data.truncated) {
      log.warn('Conductor worktree include was truncated during migration', {
        path: worktreeIncludePath,
        totalSize: content.data.totalSize,
      });
      return data;
    }
    const patterns = parseWorktreeInclude(content.data.content);
    if (patterns.length > 0) {
      data.files.push(CONDUCTOR_WORKTREE_INCLUDE_FILE);
      data.settings.preservePatterns = patterns;
      data.fields.push('preservePatterns');
    }
  }

  return data;
}

async function migrateConductorConfig(
  project: ProjectProvider,
  request: MigrateProjectConfigRequest,
  writer: ProjectConfigMigrationWriter
): Promise<Result<ProjectConfigMigration, UpdateProjectSettingsError>> {
  try {
    const data = await readConductorMigrationData(project, project.files);
    const migration = toConductorMigration(data);
    if (!migration) {
      return writeConfigFailed('No supported Conductor settings were found.');
    }

    return await applyProjectConfigMigration(project, request, data, migration, writer);
  } catch (error) {
    log.warn('Failed to migrate Conductor config to project config', { error });
    return writeConfigFailed(errorMessage(error));
  }
}

export const conductorConfigMigrator: ProjectConfigMigrator = {
  provider: 'conductor',
  inspect: async (project, files) =>
    toConductorMigration(await readConductorMigrationData(project, files)),
  migrate: migrateConductorConfig,
};
