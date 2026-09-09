import { toast } from '@emdash/ui/react/primitives';
import { when } from 'mobx';
import { useCallback, useRef, useState } from 'react';
import type { ProjectManagerStore } from '@core/features/projects/api/browser/stores/project-manager';
import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import type { StartProjectCreationResult } from '@core/features/projects/browser/stores/project-creation-types';
import { taskHostActionAvailability } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { newChatDraftView } from '@core/features/workbench/contributions/views';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import { basenameFromAnyPath } from '@core/primitives/path-name/api';

type ProjectManager = Pick<ProjectManagerStore, 'startProjectCreation' | 'hydrateProjectContext'>;

export interface OpenProjectFolderDependencies {
  selectDirectory(mode: OpenProjectFolderMode): Promise<string | null | undefined>;
  getProjectManager(): ProjectManager;
  createId(): string;
  waitUntilReady(projectId: string): Promise<void>;
}

export type OpenProjectFolderMode = 'scratch' | 'existing';

const browserDependencies: OpenProjectFolderDependencies = {
  // A native picker stays pending until the person selects a folder or cancels.
  selectDirectory: async (mode) =>
    await (
      await getHostClient()
    ).openSelectDirectoryDialog(
      {
        title: mode === 'scratch' ? 'Create a project' : 'Open a project',
        message:
          mode === 'scratch'
            ? 'Create a new folder, then select it.'
            : 'Choose the folder that contains your engineering files.',
      },
      { timeoutMs: 0 }
    ),
  getProjectManager: getProjectManagerStore,
  createId: () => crypto.randomUUID(),
  waitUntilReady: async (projectId) => {
    await when(() => taskHostActionAvailability(projectId).kind === 'enabled', {
      timeout: 30_000,
    });
  },
};

export async function openProjectFolder(
  mode: OpenProjectFolderMode = 'existing',
  dependencies: OpenProjectFolderDependencies = browserDependencies
): Promise<string | null> {
  const path = await dependencies.selectDirectory(mode);
  if (!path) return null;

  const name = basenameFromAnyPath(path);
  if (!name) throw new Error('The selected folder does not have a usable name.');

  const manager = dependencies.getProjectManager();
  const creation: StartProjectCreationResult = await manager.startProjectCreation(
    { type: 'local' },
    {
      mode: 'pick',
      name,
      path,
      initGitRepository: false,
    },
    { id: dependencies.createId() }
  );
  const projectId = creation.projectId;

  if (creation.kind === 'creating') {
    const completion = await creation.completion;
    if (!completion.success) throw new Error(projectCreationErrorMessage(completion.error));
  }

  await manager.hydrateProjectContext(projectId);
  await dependencies.waitUntilReady(projectId);
  return projectId;
}

function projectCreationErrorMessage(error: unknown): string {
  if (
    error &&
    typeof error === 'object' &&
    'message' in error &&
    typeof error.message === 'string'
  ) {
    return error.message;
  }
  return 'The project folder could not be opened.';
}

export function useOpenProjectFolder() {
  const inFlight = useRef(false);
  const [opening, setOpening] = useState(false);

  const open = useCallback(async (mode: OpenProjectFolderMode = 'existing') => {
    if (inFlight.current) return null;
    inFlight.current = true;
    setOpening(true);
    try {
      const projectId = await openProjectFolder(mode);
      if (!projectId) return null;
      getNavigation().navigate(newChatDraftView(projectId));
      return projectId;
    } catch (error) {
      toast.error('Could not open the project folder', {
        description: error instanceof Error ? error.message : String(error),
      });
      return null;
    } finally {
      inFlight.current = false;
      setOpening(false);
    }
  }, []);

  return {
    open,
    busy: opening,
  };
}
