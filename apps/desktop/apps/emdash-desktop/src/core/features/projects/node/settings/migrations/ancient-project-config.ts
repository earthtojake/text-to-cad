import { emdashConfigSchema } from '@emdash/core/primitives/emdash-config/api';
import type { Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import { remoteNameFromQualifiedRef } from '@core/primitives/git/api';
import {
  mergeShareableProjectSettings,
  type ShareableProjectSettings,
} from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import { fileKey, type FilesClientScope } from '@core/services/runtime-broker/node/files';
import { compactUndefined, parseJsonObject, readJson } from '../project-settings-json';
import type { ProjectSettingsStorage, StoredProjectSettings } from '../project-settings-storage';
import {
  hasLegacyShareableConfigMigrated,
  serializeShareableProjectSettings,
} from './legacy-shareable-marker';
import {
  legacyBaseProjectSettingsSchema,
  legacyProjectConfigSchema,
  type LegacyBaseProjectSettings,
} from './legacy-stored-project-settings';

export type AncientProjectConfigMigrationArgs = {
  projectId: string;
  row: StoredProjectSettings | undefined;
  configFiles: FilesClientScope | undefined;
  configPath: string;
  defaultBranchFallback: string | null;
  storage: ProjectSettingsStorage;
  git?: ProjectSettingsGitInspector;
  normalizeStoredWorktreeDirectory: (
    worktreeDirectory: string
  ) => Promise<Result<string, UpdateProjectSettingsError>>;
};

export type ProjectSettingsGitInspector = {
  isFileCleanlyTracked(filePath: string): Promise<boolean>;
};

function normalizeLegacyDefaultBranch(
  branch: LegacyBaseProjectSettings['defaultBranch'],
  remote: string | undefined,
  fallback: string | null
): LegacyBaseProjectSettings['defaultBranch'] {
  if (!branch) return undefined;
  if (typeof branch === 'object' && 'branch' in branch) return branch;
  const branchName = typeof branch === 'string' ? branch.trim() : branch.name.trim();
  if (!branchName) return undefined;
  if (branchName.includes('/')) return branchName;
  const remoteName =
    remote?.trim() || (fallback !== null ? remoteNameFromQualifiedRef(fallback) : undefined);
  return remoteName ? `${remoteName}/${branchName}` : branchName;
}

async function readAncientProjectConfig(
  configFiles: FilesClientScope | undefined,
  configPath: string
): Promise<LegacyBaseProjectSettings | undefined> {
  if (!configFiles) return undefined;
  try {
    const exists = await configFiles.client.fs.exists(fileKey(configFiles, configPath));
    if (!exists.success) {
      log.warn('Failed to check legacy .emdash.json for migration', exists.error);
      return undefined;
    }
    if (!exists.data.exists) return undefined;
    const content = await configFiles.client.fs.readText(fileKey(configFiles, configPath));
    if (!content.success) {
      log.warn('Failed to read legacy .emdash.json for migration', content.error);
      return undefined;
    }
    if (content.data.truncated) {
      log.warn('Legacy .emdash.json was truncated during migration', {
        path: configPath,
        totalSize: content.data.totalSize,
      });
      return undefined;
    }
    const parsed = legacyProjectConfigSchema.safeParse(parseJsonObject(content.data.content));
    if (!parsed.success) {
      log.warn('Failed to parse legacy .emdash.json for migration', { error: parsed.error });
      return undefined;
    }
    return parsed.data;
  } catch (error) {
    log.warn('Failed to read legacy .emdash.json for migration', { error });
    return undefined;
  }
}

export async function migrateAncientProjectConfig({
  projectId,
  row,
  configFiles,
  configPath,
  defaultBranchFallback,
  storage,
  git,
  normalizeStoredWorktreeDirectory,
}: AncientProjectConfigMigrationArgs): Promise<void> {
  if (!row) return;

  const baseAlreadyMigrated = Boolean(row.legacyConfigMigratedAt);
  const shareableAlreadyMigrated = hasLegacyShareableConfigMigrated(
    row.shareableProjectSettingsJson
  );
  if (baseAlreadyMigrated && shareableAlreadyMigrated) return;

  const current = readJson(
    row.baseProjectSettingsJson,
    legacyBaseProjectSettingsSchema,
    'base project settings'
  );
  const currentShareable = readJson(
    row.shareableProjectSettingsJson,
    emdashConfigSchema,
    'shareable project settings'
  );
  const { remote, ...currentSettings } = current;
  const legacy = await readAncientProjectConfig(configFiles, configPath);
  const next: Omit<LegacyBaseProjectSettings, 'remote'> = {
    ...currentSettings,
    ...(currentSettings.baseRemote === undefined && remote !== undefined
      ? { baseRemote: remote }
      : {}),
  };
  let nextShareable: ShareableProjectSettings | undefined;

  if (legacy && !baseAlreadyMigrated) {
    if (legacy.worktreeDirectory !== undefined) {
      const normalized = await normalizeStoredWorktreeDirectory(legacy.worktreeDirectory);
      if (normalized.success) next.worktreeDirectory = normalized.data;
    }
    if (legacy.remote !== undefined) next.baseRemote = legacy.remote;
    if (legacy.baseRemote !== undefined) next.baseRemote = legacy.baseRemote;
    if (legacy.pushRemote !== undefined) next.pushRemote = legacy.pushRemote;
    if (legacy.defaultBranch !== undefined) {
      next.defaultBranch = normalizeLegacyDefaultBranch(
        legacy.defaultBranch,
        legacy.baseRemote ?? legacy.remote ?? next.baseRemote,
        defaultBranchFallback
      );
    }
    if (legacy.tmux !== undefined) next.tmux = legacy.tmux;
  }

  if (legacy && !shareableAlreadyMigrated) {
    if ((await git?.isFileCleanlyTracked(configPath)) === false) {
      const legacyShareable = emdashConfigSchema.parse(legacy);
      nextShareable = mergeShareableProjectSettings(currentShareable, legacyShareable);
    }
  }

  const update: Partial<StoredProjectSettings> = {
    ...(nextShareable
      ? {
          shareableProjectSettingsJson: serializeShareableProjectSettings(nextShareable, {
            previousRaw: row.shareableProjectSettingsJson,
            markLegacyShareableConfigMigrated: true,
          }),
        }
      : {}),
  };

  if (!baseAlreadyMigrated) {
    update.baseProjectSettingsJson = JSON.stringify(compactUndefined(next));
    update.legacyConfigMigratedAt = new Date().toISOString();
  }

  if (Object.keys(update).length > 0) {
    await storage.update(projectId, update);
  }
}
