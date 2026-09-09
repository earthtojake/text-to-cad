import { homedir } from 'node:os';
import { join } from 'node:path';
import type { LocalProjectSettings } from '@core/primitives/app-settings/api';
import { defineSettingsContribution } from '@core/primitives/settings/api';
import { localProjectSettingsSchemaContribution } from '../contributions/settings';
import { getDefaultLocalWorktreeDirectory } from './worktree-defaults';

// The schema is contributed from the shared contributions surface; the
// defaults need node APIs (home directory), so the full contribution is
// assembled here and aggregated by the node settings manifest.
export const localProjectSettingsContribution = defineSettingsContribution<
  'localProject',
  LocalProjectSettings
>({
  ...localProjectSettingsSchemaContribution,
  defaults: () => ({
    defaultProjectsDirectory: join(homedir(), 'emdash', 'repositories'),
    defaultWorktreeDirectory: getDefaultLocalWorktreeDirectory(),
  }),
});
