import { z } from 'zod';
import type { NotificationSettings } from '@core/primitives/app-settings/api';
import { defineSettingsContribution } from '@core/primitives/settings/api';

const notificationSettingsSchema = z.object({
  enabled: z.boolean(),
  sound: z.boolean(),
  customSoundPath: z.string(),
  osNotifications: z.boolean(),
  soundFocusMode: z.enum(['always', 'unfocused']),
});

export const notificationSettingsContribution = defineSettingsContribution<
  'notifications',
  NotificationSettings
>({
  key: 'notifications',
  schema: notificationSettingsSchema,
  defaults: {
    enabled: true,
    sound: true,
    customSoundPath: '',
    osNotifications: true,
    soundFocusMode: 'always',
  },
});
