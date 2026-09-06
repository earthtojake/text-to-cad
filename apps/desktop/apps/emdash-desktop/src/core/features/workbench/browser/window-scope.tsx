import { toast } from '@emdash/ui/react/primitives';
import { useLayoutEffect, type ReactNode } from 'react';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { toggleAppTheme } from '@core/features/settings/api/browser/theme-toggle';
import {
  getRegisteredTaskData,
  taskHostActionAvailability,
} from '@core/features/tasks/api/browser/task-state/task-selectors';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { applyHistoryEntry } from '@core/features/workbench/browser/nav-buttons';
import { useWorkspaceLayoutContext } from '@core/features/workbench/contributions/browser/layout-provider';
import { homeViewDef, newChatDraftView } from '@core/features/workbench/contributions/views';
import { openModal } from '@core/manifests/browser/modal-api';
import { windowScope } from '@core/manifests/browser/scope-catalog';
import { confirmRegistry } from '@core/primitives/keybindings/browser';
import {
  useViewParams,
  useWorkspaceSlots,
} from '@core/primitives/navigation/browser/navigation-hooks';
import {
  getNavigation,
  getNavigationHistory,
} from '@core/primitives/navigation/browser/navigation-selectors';
import { toggleSettingsView } from '@core/primitives/navigation/browser/settings-toggle';
import { openInCommandRegistry } from '@core/primitives/open-in-apps/browser/open-in-command-registry';
import { disabled, enabled, hidden, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { scopes } from '@core/primitives/view-scopes/browser';
import { useViewScope, ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';

export function WindowScope({ children }: { readonly children: ReactNode }) {
  const { currentView } = useWorkspaceSlots();
  const taskParams = useViewParams(taskViewDef);
  const projectParams = useViewParams(projectViewDef);
  const homeParams = useViewParams(homeViewDef);
  const { toggleLeftSidebar, toggleZenMode } = useWorkspaceLayoutContext();

  const currentProjectId =
    currentView === 'task'
      ? taskParams?.projectId
      : currentView === 'project'
        ? projectParams?.projectId
        : currentView === 'home'
          ? homeParams?.projectId
          : undefined;
  const currentTaskId = currentView === 'task' ? taskParams?.taskId : undefined;
  const implementation = {
    'app.settings': () => ({
      execute: () => toggleSettingsView(),
    }),
    'app.newProject': () => ({
      execute: () => void openModal('addProjectModal', {}),
    }),
    'app.newTask': () => ({
      availability: () =>
        !currentProjectId || taskHostActionAvailability(currentProjectId).kind === 'enabled'
          ? enabled
          : disabled('This project is still opening.'),
      execute: (input) => {
        const projectId = input?.projectId ?? currentProjectId;
        getNavigation().navigate(newChatDraftView(projectId));
      },
    }),
    'app.giveFeedback': () => ({
      execute: () => {
        void openModal('feedbackModal', {});
      },
    }),
    'app.toggleTheme': () => ({
      execute: () => {
        void toggleAppTheme().then((result) => {
          if (result.success) return;
          toast.error('Theme not changed', { description: result.error.message });
        });
      },
    }),
    'app.navigateBack': () => ({
      availability: () =>
        getNavigationHistory().canGoBack ? enabled : disabled('No previous location'),
      execute: () => getNavigationHistory().back(applyHistoryEntry),
    }),
    'app.navigateForward': () => ({
      availability: () =>
        getNavigationHistory().canGoForward ? enabled : disabled('No next location'),
      execute: () => getNavigationHistory().forward(applyHistoryEntry),
    }),
    'app.commandPalette': () => ({
      execute: () => {
        const workspaceId =
          currentProjectId && currentTaskId
            ? (getRegisteredTaskData(currentProjectId, currentTaskId)?.workspaceId ?? undefined)
            : undefined;
        void openModal('commandPaletteModal', {
          projectId: currentProjectId,
          taskId: currentTaskId,
          workspaceId,
        });
      },
    }),
    'app.openInEditor': () => ({
      availability: () => (openInCommandRegistry.get() ? enabled : hidden),
      execute: () => openInCommandRegistry.get()?.trigger(),
    }),
    'app.confirm': () => ({
      availability: () => (confirmRegistry.current?.isEnabled() ? enabled : hidden),
      execute: () => confirmRegistry.current?.trigger(),
    }),
    'workbench.toggleLeftSidebar': () => ({
      execute: () => toggleLeftSidebar(),
    }),
    // Zen is workspace-chrome data; the task sidebar hides while zen is
    // active as a derived condition (no task-chrome mutation).
    'workbench.zenMode': () => ({
      execute: () => toggleZenMode(),
    }),
  } satisfies ViewScopeImpl<typeof windowScope>;

  const { instance } = useViewScope(windowScope(), implementation);

  useLayoutEffect(() => {
    if (instance) scopes.activate(instance);
  }, [instance]);

  if (!instance) return null;
  return <ViewScopeInstanceProvider instance={instance}>{children}</ViewScopeInstanceProvider>;
}
