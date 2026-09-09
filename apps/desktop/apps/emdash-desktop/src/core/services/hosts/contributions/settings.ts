import { z } from 'zod';
import type { HostSettings } from '@core/primitives/app-settings/api';
import { defineSettingsSchemaContribution } from '@core/primitives/settings/api';

const hostSettingsSchema = z.object({
  installBaseUrl: z.string(),
});

// The persisted settings key stays 'remoteMachine': it is stored in the app
// settings table and must not change in a structural rename.
// Defaults read process.env, so the full contribution (schema + defaults)
// lives in ../node/settings; only the environment-neutral schema is
// contributed here.
export const hostSettingsSchemaContribution = defineSettingsSchemaContribution<
  'remoteMachine',
  HostSettings
>({
  key: 'remoteMachine',
  schema: hostSettingsSchema,
});
