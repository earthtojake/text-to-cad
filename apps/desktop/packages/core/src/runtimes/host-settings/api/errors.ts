import { z } from 'zod';

export const hostSettingsErrorSchema = z.object({
  type: z.literal('io-failed'),
  message: z.string(),
});

export type HostSettingsError = z.infer<typeof hostSettingsErrorSchema>;
