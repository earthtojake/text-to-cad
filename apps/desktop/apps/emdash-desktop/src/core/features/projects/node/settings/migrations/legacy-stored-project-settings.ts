import {
  emdashConfigSchema,
  type EmdashConfig,
  type EmdashScriptsConfig,
} from '@emdash/core/primitives/emdash-config/api';
import z from 'zod';
import {
  baseProjectSettingsSchema,
  defaultBranchSettingSchema,
  storedDefaultBranchSchema,
  storedGithubAccountSchema,
  type StoredBaseProjectSettings,
} from '@core/primitives/project-settings/api';

export type LegacyLifecycleSettings = {
  preservePatterns?: string[];
  scripts?: EmdashScriptsConfig;
  autoRunSetup?: boolean;
  autoRunRun?: boolean;
};

/**
 * Migration-only reader for historical base-settings JSON. Current production
 * writers use StoredBaseProjectSettings and must never emit these retired keys.
 */
export const legacyBaseProjectSettingsSchema = baseProjectSettingsSchema.extend({
  remote: z.string().optional(),
  defaultBranch: z.union([defaultBranchSettingSchema, storedDefaultBranchSchema]).optional(),
  worktreeRoot: z.string().trim().optional(),
  githubAccount: storedGithubAccountSchema.optional(),
  tmuxDefaultMigrated: z.literal(true).optional(),
});

export type LegacyBaseProjectSettings = z.infer<typeof legacyBaseProjectSettingsSchema>;

/** Historical `.emdash.json` reader used only by the one-time DB/config migration. */
export const legacyProjectConfigSchema = legacyBaseProjectSettingsSchema.merge(emdashConfigSchema);

export function legacyLifecycleSettingsFromStored(
  base: LegacyBaseProjectSettings,
  shareable: EmdashConfig
): LegacyLifecycleSettings {
  return {
    ...(shareable.preservePatterns !== undefined
      ? { preservePatterns: [...shareable.preservePatterns] }
      : {}),
    ...(shareable.scripts ? { scripts: { ...shareable.scripts } } : {}),
    ...(base.autoRunSetupScriptOnTaskCreation !== undefined
      ? { autoRunSetup: base.autoRunSetupScriptOnTaskCreation }
      : {}),
    ...(base.autoRunRunScriptOnTaskCreation !== undefined
      ? { autoRunRun: base.autoRunRunScriptOnTaskCreation }
      : {}),
  };
}

export function hasLegacyLifecycleSettings(settings: LegacyLifecycleSettings): boolean {
  return (
    settings.preservePatterns !== undefined ||
    settings.scripts !== undefined ||
    settings.autoRunSetup !== undefined ||
    settings.autoRunRun !== undefined
  );
}

/**
 * Retains migration source in a historical row while an unrelated current DB
 * setting is updated. The source is removed only by the explicit finalizer.
 */
export function withLegacyLifecycleSettings(
  current: StoredBaseProjectSettings,
  legacy: LegacyLifecycleSettings
): Record<string, unknown> {
  return {
    ...current,
    ...(legacy.autoRunSetup !== undefined
      ? { autoRunSetupScriptOnTaskCreation: legacy.autoRunSetup }
      : {}),
    ...(legacy.autoRunRun !== undefined
      ? { autoRunRunScriptOnTaskCreation: legacy.autoRunRun }
      : {}),
  };
}
