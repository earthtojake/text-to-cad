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
  normalizedCommandLines,
  projectPath,
  writeConfigFailed,
} from './config-migration-utils';

const PASEO_CONFIG_FILE = 'paseo.json';

const paseoCommandSchema = z.union([z.string(), z.array(z.string())]);

const paseoScriptSchema = z
  .object({
    command: z.string().optional(),
    type: z.string().optional(),
    port: z.number().optional(),
  })
  .passthrough();

const paseoConfigSchema = z
  .object({
    worktree: z
      .object({
        setup: paseoCommandSchema.optional(),
        teardown: paseoCommandSchema.optional(),
        terminals: z.array(z.unknown()).optional(),
      })
      .passthrough()
      .optional(),
    scripts: z.record(z.string(), paseoScriptSchema).optional(),
  })
  .passthrough();

type PaseoMigrationData = {
  settings: ShareableProjectSettings;
  files: string[];
  fields: ShareableProjectSettingsWriteField[];
  unsupportedFields: string[];
};

function normalizeCommand(value: string | string[] | undefined): string | undefined {
  if (value === undefined) return undefined;

  const commands = Array.isArray(value) ? value : [value];
  return normalizedCommandLines(commands);
}

function toPaseoMigration(data: PaseoMigrationData): ProjectConfigMigration | null {
  if (data.fields.length === 0) return null;
  return {
    provider: 'paseo',
    label: 'Paseo',
    files: data.files,
    fields: data.fields,
    unsupportedFields: data.unsupportedFields,
  };
}

function addUnsupportedScripts(
  data: PaseoMigrationData,
  scripts: z.infer<typeof paseoConfigSchema>['scripts']
): void {
  if (!scripts) return;

  for (const [name, script] of Object.entries(scripts)) {
    if (script.command !== undefined) data.unsupportedFields.push(`scripts.${name}.command`);
    if (script.type !== undefined) data.unsupportedFields.push(`scripts.${name}.type`);
    if (script.port !== undefined) data.unsupportedFields.push(`scripts.${name}.port`);
  }
}

async function readPaseoMigrationData(
  project: ProjectProvider,
  files: FilesClientScope
): Promise<PaseoMigrationData> {
  const data: PaseoMigrationData = {
    settings: {},
    files: [],
    fields: [],
    unsupportedFields: [],
  };

  const paseoConfigPath = projectPath(project, PASEO_CONFIG_FILE);
  const exists = await files.client.fs.exists(fileKey(files, paseoConfigPath));
  if (!exists.success) {
    log.warn('Failed to inspect Paseo config for migration', exists.error);
    return data;
  }
  if (!exists.data.exists) return data;

  const content = await files.client.fs.readText(fileKey(files, paseoConfigPath));
  if (!content.success) {
    log.warn('Failed to read Paseo config for migration', content.error);
    return data;
  }
  if (content.data.truncated) {
    log.warn('Paseo config was truncated during migration', {
      path: paseoConfigPath,
      totalSize: content.data.totalSize,
    });
    return data;
  }
  const paseoConfig = paseoConfigSchema.parse(parseJsonObject(content.data.content));
  data.files.push(PASEO_CONFIG_FILE);

  addScript(data, 'scripts.setup', normalizeCommand(paseoConfig.worktree?.setup));
  addScript(data, 'scripts.teardown', normalizeCommand(paseoConfig.worktree?.teardown));
  addUnsupportedScripts(data, paseoConfig.scripts);

  if (paseoConfig.worktree?.terminals !== undefined) {
    data.unsupportedFields.push('worktree.terminals');
  }

  return data;
}

async function migratePaseoConfig(
  project: ProjectProvider,
  request: MigrateProjectConfigRequest,
  writer: ProjectConfigMigrationWriter
): Promise<Result<ProjectConfigMigration, UpdateProjectSettingsError>> {
  try {
    const data = await readPaseoMigrationData(project, project.files);
    const migration = toPaseoMigration(data);
    if (!migration) {
      return writeConfigFailed('No supported Paseo settings were found.');
    }

    return await applyProjectConfigMigration(project, request, data, migration, writer);
  } catch (error) {
    log.warn('Failed to migrate Paseo config to project config', { error });
    return writeConfigFailed(errorMessage(error));
  }
}

export const paseoConfigMigrator: ProjectConfigMigrator = {
  provider: 'paseo',
  inspect: async (project, files) => toPaseoMigration(await readPaseoMigrationData(project, files)),
  migrate: migratePaseoConfig,
};
