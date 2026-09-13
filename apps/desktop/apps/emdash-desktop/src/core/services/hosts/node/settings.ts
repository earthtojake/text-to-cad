import type { HostSettings } from '@core/primitives/app-settings/api';
import { defineSettingsContribution } from '@core/primitives/settings/api';
import { hostSettingsSchemaContribution } from '../contributions/settings';

// The schema is contributed from the shared contributions surface; the
// defaults read process.env, so the full contribution is assembled here and
// aggregated by the node settings manifest.
export const hostSettingsContribution = defineSettingsContribution<'remoteMachine', HostSettings>({
  ...hostSettingsSchemaContribution,
  defaults: () => ({
    installBaseUrl:
      process.env['HARDCORE_WORKSPACE_SERVER_ARTIFACTS_URL'] ??
      'https://github.com/amywork777/hardcore/releases/download/workspace-server',
  }),
});
