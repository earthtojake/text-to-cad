import { defaultAgentSettingsContribution } from '@core/features/agents/contributions/settings';
import {
  browserPreviewSettingsContribution,
  browserSettingsContribution,
} from '@core/features/browser/contributions/settings';
import { filesSettingsContribution } from '@core/features/editor/contributions/settings';
import {
  localProjectSettingsSchemaContribution,
  projectSettingsContribution,
} from '@core/features/projects/contributions/settings';
import { changesViewModeSettingsContribution } from '@core/features/source-control/contributions/settings';
import { taskSettingsContribution } from '@core/features/tasks/contributions/settings';
import { terminalSettingsContribution } from '@core/features/terminals/contributions/settings';
import {
  interfaceSettingsContribution,
  keyboardSettingsContribution,
  openInSettingsContribution,
  themeSettingsContribution,
} from '@core/features/workbench/contributions/settings';
import type { SettingsValues } from '@core/primitives/settings/api';
import { hostSettingsSchemaContribution } from '@core/services/hosts/contributions/settings';
import { notificationSettingsContribution } from '@core/services/notifications/contributions/settings';

/**
 * Schema-level view of every settings contribution: this manifest is shared
 * between the browser and node programs, so contributions whose defaults need
 * node APIs (localProject, remoteMachine) appear here as schema contributions
 * only. The node settings manifest overlays the full contributions with
 * defaults for the settings store.
 */
export const appSettingsSchemaContributions = {
  localProject: localProjectSettingsSchemaContribution,
  project: projectSettingsContribution,
  tasks: taskSettingsContribution,
  files: filesSettingsContribution,
  defaultAgent: defaultAgentSettingsContribution,
  keyboard: keyboardSettingsContribution,
  notifications: notificationSettingsContribution,
  theme: themeSettingsContribution,
  openIn: openInSettingsContribution,
  interface: interfaceSettingsContribution,
  terminal: terminalSettingsContribution,
  browserPreview: browserPreviewSettingsContribution,
  browser: browserSettingsContribution,
  changesViewMode: changesViewModeSettingsContribution,
  remoteMachine: hostSettingsSchemaContribution,
} as const;

export type AppSettings = SettingsValues<typeof appSettingsSchemaContributions>;
export type AppSettingsKey = keyof AppSettings;

export const AppSettingsKeys = Object.keys(appSettingsSchemaContributions) as AppSettingsKey[];
