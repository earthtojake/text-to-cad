import { defineContract, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import type { AppSettings, AppSettingsKey, SettingsMeta } from './types';

export const appSettingsDomain = 'appSettings' as const;

export const appSettingsContract = defineContract({
  get: procedure({
    input: z.object({ key: z.custom<AppSettingsKey>() }),
    output: z.custom<AppSettings[AppSettingsKey]>(),
  }),
  getAll: procedure({ input: z.void(), output: z.custom<AppSettings>() }),
  getWithMeta: procedure({
    input: z.object({ key: z.custom<AppSettingsKey>() }),
    output: z.custom<SettingsMeta<AppSettings[AppSettingsKey]>>(),
  }),
  update: procedure({
    input: z.object({
      key: z.custom<AppSettingsKey>(),
      value: z.custom<AppSettings[AppSettingsKey]>(),
    }),
    output: z.void(),
  }),
  reset: procedure({
    input: z.object({ key: z.custom<AppSettingsKey>() }),
    output: z.void(),
  }),
  resetField: procedure({
    input: z.object({ key: z.custom<AppSettingsKey>(), field: z.string() }),
    output: z.void(),
  }),
});
