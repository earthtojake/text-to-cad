import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { toast } from '@emdash/ui/react/primitives';
import { useCallback, useMemo, useRef, useState } from 'react';
import { buildCadFirstRoutingContext } from '@core/features/cad/api/browser/cad-agent';
import {
  readLastCadConversationProvider,
  rememberCadConversationProvider,
} from '@core/features/cad/api/browser/cad-conversation-provider';
import { BLANK_CHAT_TITLE } from '@core/features/conversations/api/browser/prompt-title';
import { useEffectiveProvider } from '@core/features/conversations/api/browser/use-effective-provider';
import {
  getProjectSshConnectionId,
  getProjectStore,
  projectData,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { useTaskSettings } from '@core/features/tasks/api/browser/hooks/useTaskSettings';
import { getTaskManagerStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import type { CreateTaskParams } from '@core/primitives/tasks/api';

type TaskManager = NonNullable<ReturnType<typeof getTaskManagerStore>>;

export interface StartBlankChatInput {
  projectId: string;
  providerId: AgentProviderId;
  autoApprove: boolean;
  initialPrompt?: string;
  modelId?: string;
}

export interface StartBlankChatResult {
  taskId: string;
  conversationId: string;
}

export interface StartBlankChatDependencies {
  getProject(projectId: string): ReturnType<typeof projectData>;
  getTaskManager(projectId: string): TaskManager | undefined;
  createId(): string;
  navigate(projectId: string, taskId: string): void;
}

const browserDependencies: StartBlankChatDependencies = {
  getProject: (projectId) => projectData(getProjectStore(projectId)),
  getTaskManager: getTaskManagerStore,
  createId: () => crypto.randomUUID(),
  navigate: (projectId, taskId) => {
    getNavigation().navigate(taskViewDef({ projectId, taskId }));
  },
};

export async function startBlankChat(
  input: StartBlankChatInput,
  dependencies: StartBlankChatDependencies = browserDependencies
): Promise<StartBlankChatResult> {
  const project = dependencies.getProject(input.projectId);
  if (!project?.repositoryWorkspaceId) {
    throw new Error('The project folder is still opening. Try again in a moment.');
  }

  const taskManager = dependencies.getTaskManager(input.projectId);
  if (!taskManager) {
    throw new Error('The project folder is still opening. Try again in a moment.');
  }

  await taskManager.loadTasks();

  const title = nextBlankChatTitle(
    Array.from(taskManager.tasks.values(), (task) => task.data.name)
  );
  const taskId = dependencies.createId();
  const conversationId = dependencies.createId();
  const params: CreateTaskParams = {
    id: taskId,
    projectId: input.projectId,
    taskConfig: {
      version: '1',
      name: title,
      initialConversation: {
        id: conversationId,
        provider: input.providerId,
        title,
        autoApprove: input.autoApprove,
        type: 'acp',
        ...(input.modelId ? { model: input.modelId } : {}),
        ...(input.initialPrompt?.trim()
          ? {
              initialQueue: [
                {
                  text: input.initialPrompt.trim(),
                  hiddenContext: buildCadFirstRoutingContext(),
                },
              ],
            }
          : {}),
      },
    },
    workspaceConfig: {
      version: '2',
      git: { kind: 'none' },
      workspace: {
        kind: 'repository-instance',
        workspaceId: project.repositoryWorkspaceId,
      },
    },
  };

  const creation = taskManager.createTask(params);
  await creation;
  dependencies.navigate(input.projectId, taskId);

  return { taskId, conversationId };
}

export function useStartBlankChat(defaultProjectId?: string) {
  const connectionId = defaultProjectId ? getProjectSshConnectionId(defaultProjectId) : undefined;
  const initialProvider = useMemo(
    () => readLastCadConversationProvider(window.localStorage, connectionId),
    [connectionId]
  );
  const { providerId, setProviderOverride, installedProviderIds, createDisabled } =
    useEffectiveProvider(connectionId, initialProvider);
  const { autoApproveByDefault } = useTaskSettings();
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);

  const start = useCallback(
    async (
      projectId = defaultProjectId,
      initialPrompt?: string,
      modelId?: string
    ): Promise<StartBlankChatResult | null> => {
      if (inFlight.current) return null;
      if (!projectId) {
        toast.error('Open a project folder before starting a chat.');
        return null;
      }
      if (!providerId || createDisabled) {
        toast.error('Connect Codex or Claude before starting a chat.');
        return null;
      }

      inFlight.current = true;
      setBusy(true);
      try {
        const result = await startBlankChat({
          projectId,
          providerId,
          autoApprove: autoApproveByDefault,
          initialPrompt,
          modelId,
        });
        rememberCadConversationProvider(window.localStorage, providerId, connectionId);
        return result;
      } catch (error) {
        toast.error('Could not start the chat', {
          description: error instanceof Error ? error.message : String(error),
        });
        return null;
      } finally {
        inFlight.current = false;
        setBusy(false);
      }
    },
    [autoApproveByDefault, connectionId, createDisabled, defaultProjectId, providerId]
  );

  return {
    start,
    busy,
    disabled: createDisabled,
    providerId,
    installedProviderIds,
    setProvider: setProviderOverride,
  };
}

function nextBlankChatTitle(existingTitles: readonly string[]): string {
  const used = new Set(existingTitles.map((title) => title.trim().toLowerCase()));
  if (!used.has(BLANK_CHAT_TITLE.toLowerCase())) return BLANK_CHAT_TITLE;

  let index = 2;
  while (used.has(`${BLANK_CHAT_TITLE.toLowerCase()} ${index}`)) index += 1;
  return `${BLANK_CHAT_TITLE} ${index}`;
}
