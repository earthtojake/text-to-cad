import type { Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import * as toml from 'smol-toml';
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
import type { ProjectConfigMigrationWriter, ProjectConfigMigrator } from './config-migration';
import {
  addScript,
  applyProjectConfigMigration,
  errorMessage,
  projectPath,
  trimmedText,
  writeConfigFailed,
} from './config-migration-utils';

const CODEX_ENVIRONMENT_FILE = '.codex/environments/environment.toml';

const codexScriptSectionSchema = z
  .object({
    script: z.string().optional(),
  })
  .passthrough();

const codexActionSchema = z
  .object({
    name: z.string().optional(),
    icon: z.string().optional(),
    command: z.string().optional(),
  })
  .passthrough();

const codexEnvironmentSchema = z
  .object({
    setup: codexScriptSectionSchema.optional(),
    cleanup: codexScriptSectionSchema.optional(),
    actions: z.array(codexActionSchema).optional(),
  })
  .passthrough();

type CodexMigrationData = {
  settings: ShareableProjectSettings;
  files: string[];
  fields: ShareableProjectSettingsWriteField[];
  unsupportedFields: string[];
};

function actionLabel(action: z.infer<typeof codexActionSchema>, index: number): string {
  const name = action.name?.trim();
  return name ? name : String(index);
}

function addUnsupportedActions(
  data: CodexMigrationData,
  actions: z.infer<typeof codexEnvironmentSchema>['actions']
): void {
  if (!actions) return;

  actions.forEach((action, index) => {
    const label = actionLabel(action, index);
    if (action.command !== undefined) data.unsupportedFields.push(`actions.${label}.command`);
    if (action.icon !== undefined) data.unsupportedFields.push(`actions.${label}.icon`);
  });
}

function toCodexMigration(data: CodexMigrationData): ProjectConfigMigration | null {
  if (data.fields.length === 0) return null;
  return {
    provider: 'codex',
    label: 'Codex',
    files: data.files,
    fields: data.fields,
    unsupportedFields: data.unsupportedFields,
  };
}

async function readCodexMigrationData(
  project: ProjectProvider,
  files: FilesClientScope
): Promise<CodexMigrationData> {
  const data: CodexMigrationData = {
    settings: {},
    files: [],
    fields: [],
    unsupportedFields: [],
  };

  const environmentPath = projectPath(project, CODEX_ENVIRONMENT_FILE);
  const exists = await files.client.fs.exists(fileKey(files, environmentPath));
  if (!exists.success) {
    log.warn('Failed to inspect Codex environment file for migration', exists.error);
    return data;
  }
  if (!exists.data.exists) return data;

  const content = await files.client.fs.readText(fileKey(files, environmentPath));
  if (!content.success) {
    log.warn('Failed to read Codex environment file for migration', content.error);
    return data;
  }
  if (content.data.truncated) {
    log.warn('Codex environment file was truncated during migration', {
      path: environmentPath,
      totalSize: content.data.totalSize,
    });
    return data;
  }
  const codexEnvironment = codexEnvironmentSchema.parse(toml.parse(content.data.content));
  data.files.push(CODEX_ENVIRONMENT_FILE);

  addScript(data, 'scripts.setup', trimmedText(codexEnvironment.setup?.script));
  addScript(data, 'scripts.teardown', trimmedText(codexEnvironment.cleanup?.script));
  addUnsupportedActions(data, codexEnvironment.actions);

  return data;
}

async function migrateCodexConfig(
  project: ProjectProvider,
  request: MigrateProjectConfigRequest,
  writer: ProjectConfigMigrationWriter
): Promise<Result<ProjectConfigMigration, UpdateProjectSettingsError>> {
  try {
    const data = await readCodexMigrationData(project, project.files);
    const migration = toCodexMigration(data);
    if (!migration) {
      return writeConfigFailed('No supported Codex settings were found.');
    }

    return await applyProjectConfigMigration(project, request, data, migration, writer);
  } catch (error) {
    log.warn('Failed to migrate Codex config to project config', { error });
    return writeConfigFailed(errorMessage(error));
  }
}

export const codexConfigMigrator: ProjectConfigMigrator = {
  provider: 'codex',
  inspect: async (project, files) => toCodexMigration(await readCodexMigrationData(project, files)),
  migrate: migrateCodexConfig,
};
