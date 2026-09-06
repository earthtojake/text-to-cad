import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { OverrideSettings } from './override-settings';
import { migrateProviderConfigOverrides } from './provider-config-migrations';
import { providerConfigDefaults, providerCustomConfigEntrySchema } from './provider-config-schema';

export type ProviderOverrideSettings = OverrideSettings<ProviderCustomConfig>;

export function createProviderOverrideSettings(db: AppDb): ProviderOverrideSettings {
  return new OverrideSettings<ProviderCustomConfig>(
    db,
    'providerConfigs',
    () => providerConfigDefaults,
    providerCustomConfigEntrySchema,
    migrateProviderConfigOverrides
  );
}
