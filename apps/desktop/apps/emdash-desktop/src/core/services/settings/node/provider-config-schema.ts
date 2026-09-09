import { z } from 'zod';
import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';

export const providerCustomConfigEntrySchema: z.ZodType<ProviderCustomConfig> = z.object({
  extraArgs: z.string().optional(),
  env: z.record(z.string(), z.string()).optional(),
});

export const providerConfigDefaults: Record<string, ProviderCustomConfig> = {};
