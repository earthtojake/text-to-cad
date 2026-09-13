import { z } from 'zod';
import type { BrowserSettings } from '@core/primitives/app-settings/api';
import {
  BROWSER_ISOLATED_PROFILE_ID,
  DEFAULT_BROWSER_PROFILE_ID,
  DEFAULT_BROWSER_PROFILES,
} from '@core/primitives/browser/api';
import { defineSettingsContribution } from '@core/primitives/settings/api';

const browserProfileIdSchema = z
  .string()
  .regex(/^[a-z0-9][a-z0-9-]{0,63}$/)
  .refine((value) => value !== BROWSER_ISOLATED_PROFILE_ID);

const browserSettingsSchema = z
  .object({
    defaultProfileId: z.union([browserProfileIdSchema, z.literal(BROWSER_ISOLATED_PROFILE_ID)]),
    relaxCorsForLocalhost: z.boolean(),
    profiles: z
      .array(
        z.object({
          id: browserProfileIdSchema,
          name: z.string().trim().min(1).max(40),
        })
      )
      .min(1),
  })
  .refine(
    (settings) =>
      new Set(settings.profiles.map((profile) => profile.id)).size === settings.profiles.length
  )
  .refine(
    (settings) =>
      settings.defaultProfileId === BROWSER_ISOLATED_PROFILE_ID ||
      settings.profiles.some((profile) => profile.id === settings.defaultProfileId)
  );

export const browserSettingsContribution = defineSettingsContribution<'browser', BrowserSettings>({
  key: 'browser',
  schema: browserSettingsSchema,
  defaults: {
    defaultProfileId: DEFAULT_BROWSER_PROFILE_ID,
    relaxCorsForLocalhost: false,
    profiles: DEFAULT_BROWSER_PROFILES,
  },
});

export const browserPreviewSettingsContribution = defineSettingsContribution<
  'browserPreview',
  { enabled: boolean }
>({
  key: 'browserPreview',
  schema: z.object({ enabled: z.boolean() }),
  defaults: { enabled: true },
});
