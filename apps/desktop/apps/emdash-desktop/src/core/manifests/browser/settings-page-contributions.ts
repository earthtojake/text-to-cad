import { promptsSettingsPage } from '@core/features/library/contributions/settings-page';
import {
  conversationsSettingsPage,
  localWorkspacesSettingsPage,
  machinesConnectionsPage,
  systemSettingsPage,
} from '@core/features/machines/contributions/settings-page';
import { mcpSettingsPage } from '@core/features/mcp/contributions/settings-page';
import {
  agentsSettingsPage,
  browserSettingsPage,
  generalSettingsPage,
  interfaceSettingsPage,
  repositorySettingsPage,
} from '@core/features/settings/contributions/settings-pages';
import type { SettingsPageTab } from '@core/features/settings/contributions/views';
import { skillsSettingsPage } from '@core/features/skills/contributions/settings-page';
import type { SettingsPageContribution } from '@core/primitives/settings/api/page-contribution';

export const settingsPageContributions = [
  generalSettingsPage,
  interfaceSettingsPage,
  browserSettingsPage,
  repositorySettingsPage,
  promptsSettingsPage,
  systemSettingsPage,
  localWorkspacesSettingsPage,
  conversationsSettingsPage,
  agentsSettingsPage,
  mcpSettingsPage,
  skillsSettingsPage,
  machinesConnectionsPage,
] as const satisfies readonly SettingsPageContribution<Exclude<SettingsPageTab, 'docs'>>[];
