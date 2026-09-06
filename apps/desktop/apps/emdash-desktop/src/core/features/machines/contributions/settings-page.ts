import { getMachinesStore } from '@core/features/machines/contributions/app-stores';
import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import type { SettingsPageTab } from '@core/features/settings/contributions/views';
import {
  defineSettingsPageContribution,
  type SettingsPageContribution,
} from '@core/primitives/settings/api/page-contribution';
import { ConversationsSettingsPage } from '../browser/pages/conversations-settings-page';
import { LocalWorkspacesSettingsPage } from '../browser/pages/local-workspaces-settings-page';
import {
  MachineDetailsPage,
  MachineWorkspaceDetailPage,
} from '../browser/pages/machine-details-page';
import { MachinesSettingsPage } from '../browser/pages/machines-settings-page';
import { SystemSettingsPage } from '../browser/pages/system-settings-page';
import { LocalWorkspaceDetailPage } from '../browser/pages/workspace-detail-page';

function projectBreadcrumbLabel(path: string[]): string | null {
  const projectId = path.at(-1);
  return projectId ? (getProjectManagerStore().projects.get(projectId)?.data?.name ?? null) : null;
}

export const systemSettingsPage = defineSettingsPageContribution({
  id: 'system',
  label: 'System',
  icon: 'activity',
  component: SystemSettingsPage,
} satisfies SettingsPageContribution<SettingsPageTab>);

export const localWorkspacesSettingsPage = defineSettingsPageContribution({
  id: 'workspaces-local',
  label: 'Workspaces',
  icon: 'folder-git-2',
  component: LocalWorkspacesSettingsPage,
  detail: {
    component: LocalWorkspaceDetailPage,
    breadcrumbLabel: projectBreadcrumbLabel,
  },
} satisfies SettingsPageContribution<SettingsPageTab>);

export const conversationsSettingsPage = defineSettingsPageContribution({
  id: 'conversations',
  label: 'Conversations',
  icon: 'message-square',
  component: ConversationsSettingsPage,
} satisfies SettingsPageContribution<SettingsPageTab>);

export const machinesConnectionsPage = defineSettingsPageContribution({
  id: 'connections',
  label: 'Machines',
  icon: 'server',
  component: MachinesSettingsPage,
  detail: {
    component: MachineDetailsPage,
    breadcrumbLabel: (path) =>
      getMachinesStore().connections.find((connection) => connection.id === path.at(-1))?.name ??
      null,
    child: {
      component: MachineWorkspaceDetailPage,
      breadcrumbLabel: projectBreadcrumbLabel,
    },
  },
} satisfies SettingsPageContribution<SettingsPageTab>);
