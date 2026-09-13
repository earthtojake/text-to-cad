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
  applyProjectConfigMigration,
  errorMessage,
  normalizedCommandLines,
  projectPath,
  setScript,
  writeConfigFailed,
} from './config-migration-utils';

const SUPERSET_CONFIG_FILE = '.superset/config.json';

const supersetScriptOverrideSchema = z
  .object({
    before: z.array(z.string()).optional(),
    after: z.array(z.string()).optional(),
  })
  .passthrough();

const supersetScriptSchema = z.union([z.array(z.string()), supersetScriptOverrideSchema]);

const supersetConfigSchema = z
  .object({
    setup: supersetScriptSchema.optional(),
    teardown: supersetScriptSchema.optional(),
    run: supersetScriptSchema.optional(),
  })
  .passthrough();

type SupersetScriptConfig = z.infer<typeof supersetScriptSchema>;

type SupersetMigrationData = {
  settings: ShareableProjectSettings;
  files: string[];
  fields: ShareableProjectSettingsWriteField[];
  unsupportedFields: string[];
};

const SUPERSET_SCRIPT_FIELDS = [
  { source: 'setup', target: 'scripts.setup' },
  { source: 'run', target: 'scripts.run' },
  { source: 'teardown', target: 'scripts.teardown' },
] as const satisfies Array<{
  source: 'setup' | 'run' | 'teardown';
  target: ShareableProjectSettingsWriteField;
}>;

function addUnsupportedOverrideFields(
  data: SupersetMigrationData,
  source: 'setup' | 'run' | 'teardown',
  script: SupersetScriptConfig
): void {
  if (Array.isArray(script)) return;
  if (script.before !== undefined) data.unsupportedFields.push(`${source}.before`);
  if (script.after !== undefined) data.unsupportedFields.push(`${source}.after`);
}

function toSupersetMigration(data: SupersetMigrationData): ProjectConfigMigration | null {
  if (data.fields.length === 0) return null;
  return {
    provider: 'superset',
    label: 'Superset',
    files: data.files,
    fields: data.fields,
    unsupportedFields: data.unsupportedFields,
  };
}

async function readSupersetMigrationData(
  project: ProjectProvider,
  files: FilesClientScope
): Promise<SupersetMigrationData> {
  const data: SupersetMigrationData = {
    settings: {},
    files: [],
    fields: [],
    unsupportedFields: [],
  };

  const supersetConfigPath = projectPath(project, SUPERSET_CONFIG_FILE);
  const exists = await files.client.fs.exists(fileKey(files, supersetConfigPath));
  if (!exists.success) {
    log.warn('Failed to inspect Superset config for migration', exists.error);
    return data;
  }
  if (!exists.data.exists) return data;

  const content = await files.client.fs.readText(fileKey(files, supersetConfigPath));
  if (!content.success) {
    log.warn('Failed to read Superset config for migration', content.error);
    return data;
  }
  if (content.data.truncated) {
    log.warn('Superset config was truncated during migration', {
      path: supersetConfigPath,
      totalSize: content.data.totalSize,
    });
    return data;
  }
  const config = supersetConfigSchema.parse(parseJsonObject(content.data.content));
  data.files.push(SUPERSET_CONFIG_FILE);

  for (const { source, target } of SUPERSET_SCRIPT_FIELDS) {
    const script = config[source];
    if (script === undefined) continue;

    if (Array.isArray(script)) {
      const value = normalizedCommandLines(script);
      if (!value) continue;
      setScript(data.settings, target, value);
      data.fields.push(target);
      continue;
    }

    addUnsupportedOverrideFields(data, source, script);
  }

  return data;
}

async function migrateSupersetConfig(
  project: ProjectProvider,
  request: MigrateProjectConfigRequest,
  writer: ProjectConfigMigrationWriter
): Promise<Result<ProjectConfigMigration, UpdateProjectSettingsError>> {
  try {
    const data = await readSupersetMigrationData(project, project.files);
    const migration = toSupersetMigration(data);
    if (!migration) {
      return writeConfigFailed('No supported Superset settings were found.');
    }

    return await applyProjectConfigMigration(project, request, data, migration, writer);
  } catch (error) {
    log.warn('Failed to migrate Superset config to project config', { error });
    return writeConfigFailed(errorMessage(error));
  }
}

export const supersetConfigMigrator: ProjectConfigMigrator = {
  provider: 'superset',
  inspect: async (project, files) =>
    toSupersetMigration(await readSupersetMigrationData(project, files)),
  migrate: migrateSupersetConfig,
};
