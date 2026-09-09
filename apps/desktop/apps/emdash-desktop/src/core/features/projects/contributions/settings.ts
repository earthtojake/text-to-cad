import { z } from 'zod';
import type { LocalProjectSettings, ProjectSettings } from '@core/primitives/app-settings/api';
import {
  defineSettingsContribution,
  defineSettingsSchemaContribution,
} from '@core/primitives/settings/api';
import { normalizeBranchPrefix } from '@core/primitives/tasks/api';

const projectSettingsSchema = z.object({
  pushOnCreate: z.boolean(),
  branchPrefix: z.string().transform(normalizeBranchPrefix),
  appendRandomBranchSuffix: z.boolean(),
  tmuxByDefault: z.boolean(),
});

const localProjectSettingsSchema = z.object({
  defaultProjectsDirectory: z.string(),
  defaultWorktreeDirectory: z.string(),
});

export const projectSettingsContribution = defineSettingsContribution<'project', ProjectSettings>({
  key: 'project',
  schema: projectSettingsSchema,
  defaults: {
    pushOnCreate: true,
    branchPrefix: 'emdash',
    appendRandomBranchSuffix: true,
    tmuxByDefault: false,
  },
});

// Defaults are computed from the local home directory, so the full
// contribution (schema + defaults) lives in ../node/settings; only the
// environment-neutral schema is contributed here.
export const localProjectSettingsSchemaContribution = defineSettingsSchemaContribution<
  'localProject',
  LocalProjectSettings
>({
  key: 'localProject',
  schema: localProjectSettingsSchema,
});
