import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import type {
  MigrateProjectConfigRequest,
  ProjectConfigMigration,
  ShareableProjectSettings,
  ShareableProjectSettingsWriteField,
} from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import { fileKey, fsErrorMessage } from '@core/services/runtime-broker/node/files';
import type { ProjectConfigMigrationWriter } from './config-migration';
import { CONFIG_FILE } from './workspace-config-file';

type ScriptField = Extract<ShareableProjectSettingsWriteField, `scripts.${string}`>;

export type MigrationSettingsData = {
  settings: ShareableProjectSettings;
  fields: ShareableProjectSettingsWriteField[];
};

export function writeConfigFailed<T = never>(
  message: string
): Result<T, UpdateProjectSettingsError> {
  return err({ type: 'write-config-failed', message });
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function projectPath(project: ProjectProvider, relPath: string): string {
  return project.resolveProjectPath(relPath);
}

export function trimmedText(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

export function normalizedCommandLines(commands: string[]): string | undefined {
  const normalized = commands.map((command) => command.trim()).filter(Boolean);
  return normalized.length > 0 ? normalized.join('\n') : undefined;
}

export function setScript(
  settings: ShareableProjectSettings,
  field: ScriptField,
  value: string
): void {
  settings.scripts ??= {};
  if (field === 'scripts.prepare') settings.scripts.prepare = value;
  if (field === 'scripts.setup') settings.scripts.setup = value;
  if (field === 'scripts.run') settings.scripts.run = value;
  if (field === 'scripts.teardown') settings.scripts.teardown = value;
}

export function addScript(
  data: MigrationSettingsData,
  field: ScriptField,
  value: string | undefined
): void {
  if (!value) return;
  setScript(data.settings, field, value);
  data.fields.push(field);
}

export async function applyProjectConfigMigration(
  project: ProjectProvider,
  request: MigrateProjectConfigRequest,
  data: MigrationSettingsData,
  migration: ProjectConfigMigration,
  writer: ProjectConfigMigrationWriter
): Promise<Result<ProjectConfigMigration, UpdateProjectSettingsError>> {
  if (request.destination === 'local') {
    const updateResult = await writer.patchPersonalConfig({
      ...(data.settings.preservePatterns !== undefined
        ? { preservePatterns: [...data.settings.preservePatterns] }
        : {}),
      ...(data.settings.scripts ? { scripts: { ...data.settings.scripts } } : {}),
    });
    if (!updateResult.success) return updateResult;
    return ok(migration);
  }

  const configPath = projectPath(project, CONFIG_FILE);
  const written = await project.files.client.fs.writeFile({
    ...fileKey(project.files, configPath),
    content: `${JSON.stringify(data.settings, null, 2)}\n`,
    precondition: { kind: 'overwrite' },
  });
  if (!written.success) {
    return writeConfigFailed(`Could not write ${CONFIG_FILE}: ${fsErrorMessage(written.error)}`);
  }

  const clearResult = await writer.clearPersonalFields(data.fields);
  if (!clearResult.success) {
    log.warn('Failed to clear imported local project settings', clearResult.error);
    return writeConfigFailed(`Wrote ${CONFIG_FILE}, but failed to clear local project settings.`);
  }

  return ok(migration);
}
