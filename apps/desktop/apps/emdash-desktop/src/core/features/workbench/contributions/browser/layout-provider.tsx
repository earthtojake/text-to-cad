import type { LayoutStorage } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  asAvailableProject,
  getProjectStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import type { WorkspaceChromeStore } from '@core/features/projects/api/browser/stores/workspace-chrome-store';
import { projectPanelLayoutsMemento } from '@core/features/projects/contributions/mementos';
import { workspaceChromeStoreToken } from '@core/features/projects/contributions/project-stores';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import type { ViewRef } from '@core/primitives/views/api';

export interface WorkspaceLayoutContextValue {
  isLeftOpen: boolean;
  isZenActive: boolean;
  toggleLeftSidebar: () => void;
  toggleZenMode: () => void;
  /**
   * Storage facade for the workspace outer layout, scoped to the active
   * project's chrome subject (spec §Persistence model editorial call);
   * ephemeral in-memory storage until a project chrome is hydrated.
   */
  layoutStorage: LayoutStorage;
  /**
   * Remount key for the outer `Resizable.Group`: the library reads
   * `defaultLayout` only at group mount, so the group must remount whenever
   * the storage subject changes (project switch or hydration completing).
   */
  layoutKey: string;
}

const WorkspaceLayoutContext = createContext<WorkspaceLayoutContextValue | undefined>(undefined);

/** Reads `projectId` from project-bearing view refs (task, project). */
function projectIdFromRef(ref: ViewRef | undefined): string | undefined {
  const projectId = (ref?.params as { projectId?: unknown } | undefined)?.projectId;
  return typeof projectId === 'string' && projectId.length > 0 ? projectId : undefined;
}

/**
 * Workspace chrome for one project, readable only once its subject space has
 * hydrated. There is no render gate at the project boundary (the task-view
 * `isHydrated` gate covers only task subjects), so callers gate here: reading
 * chrome state or the layout facade pre-hydration is a loud dev error by
 * design, never a silent reset.
 */
function hydratedWorkspaceChrome(projectId: string): WorkspaceChromeStore | undefined {
  return asAvailableProject(getProjectStore(projectId))?.get(workspaceChromeStoreToken);
}

function createEphemeralLayoutStorage(): LayoutStorage {
  const entries = new Map<string, string>();
  return {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => {
      entries.set(key, value);
    },
  };
}

export const WorkspaceLayoutContextProvider = observer(function WorkspaceLayoutContextProvider({
  children,
}: {
  children: ReactNode;
}) {
  // The active project is sticky: leaving for a project-less view (settings,
  // home) keeps the last project's chrome instead of resetting the sidebar.
  const [activeProjectId, setActiveProjectId] = useState<string | undefined>(() =>
    projectIdFromRef(getNavigation().currentRef)
  );
  // Ephemeral chrome for the no-project / pre-hydration window, so the
  // sidebar toggle still works on a fresh install's home view. Not a shadow
  // copy of store state — it feeds the view only while no chrome store exists.
  const [fallbackLeftOpen, setFallbackLeftOpen] = useState(true);

  useEffect(() => {
    return getNavigation().onDidNavigate.subscribe((event) => {
      // The implicit exit-on-navigation cleanup became this explicit command
      // at the navigation site. Only user navigation ('traversal' to another
      // view ref) exits zen; the startup 'restoration' commit does not, so
      // restarting in zen resumes zen with its persisted restore.
      if (event.kind === 'traversal' && event.from && event.from.key !== event.to.key) {
        const fromProjectId = projectIdFromRef(event.from);
        if (fromProjectId) {
          const chrome = hydratedWorkspaceChrome(fromProjectId);
          if (chrome?.state.zen.active) chrome.commands.exitZenMode();
        }
      }
      const projectId = projectIdFromRef(event.to);
      if (projectId) setActiveProjectId(projectId);
    });
  }, []);

  const context = activeProjectId
    ? asAvailableProject(getProjectStore(activeProjectId))
    : undefined;
  const chrome = context?.get(workspaceChromeStoreToken);

  const ephemeralStorage = useMemo(() => createEphemeralLayoutStorage(), []);
  const layoutStorage = useMemo(
    () => (context ? context.createLayoutStorage(projectPanelLayoutsMemento) : ephemeralStorage),
    [context, ephemeralStorage]
  );

  const state = chrome ? chrome.state : undefined;
  const value: WorkspaceLayoutContextValue = {
    isLeftOpen: state ? state.leftSidebarOpen : fallbackLeftOpen,
    isZenActive: state?.zen.active ?? false,
    toggleLeftSidebar: () => {
      if (chrome) chrome.commands.toggleLeftSidebar();
      else setFallbackLeftOpen((open) => !open);
    },
    toggleZenMode: () => {
      if (!chrome) return;
      if (chrome.state.zen.active) chrome.commands.exitZenMode();
      else chrome.commands.enterZenMode();
    },
    layoutStorage,
    layoutKey: context && activeProjectId ? `project:${activeProjectId}` : 'unscoped',
  };

  return (
    <WorkspaceLayoutContext.Provider value={value}>{children}</WorkspaceLayoutContext.Provider>
  );
});

export function useWorkspaceLayoutContext() {
  const context = useContext(WorkspaceLayoutContext);
  if (!context) {
    throw new Error(
      'useWorkspaceLayoutContext must be used within a WorkspaceLayoutContextProvider'
    );
  }
  return context;
}
