import { localProjectSettingsContribution } from '@core/features/projects/node/settings';
import type { SettingsContributionMap } from '@core/primitives/settings/api';
import { hostSettingsContribution } from '@core/services/hosts/node/settings';
import {
  appSettingsSchemaContributions,
  type AppSettings,
  type AppSettingsKey,
} from '../shared/settings-contributions';

/**
 * Full settings contributions (schema + defaults) for the node side. The
 * shared manifest carries the schema-level view for both programs; this
 * overlay adds the contributions whose defaults require node APIs.
 */
export const appSettingsContributions: SettingsContributionMap<AppSettings> = {
  ...appSettingsSchemaContributions,
  localProject: localProjectSettingsContribution,
  remoteMachine: hostSettingsContribution,
};

export function getDefaultForKey<K extends AppSettingsKey>(key: K): AppSettings[K] {
  const defaults = appSettingsContributions[key].defaults;
  return (typeof defaults === 'function' ? defaults() : defaults) as AppSettings[K];
}
