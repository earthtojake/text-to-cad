import { useCallback } from 'react';
import { getTaskManagerStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import type { InitialConversationState } from '@core/features/tasks/contributions/browser/task-config/initial-conversation-section';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { log } from '@core/primitives/logging/browser/logger';
import type { NavigateFnTyped } from '@core/primitives/navigation/browser/navigation-hooks';
import { buildInitialConversation, deriveInitialStatus } from './build-create-task-params';
import type { CreateTaskState } from './use-create-task-state';

interface UseCreateTaskCallbackParams {
  selectedProjectId: string | undefined;
  state: CreateTaskState;
  initialConversation: InitialConversationState;
  navigate: NavigateFnTyped;
  onCreated: () => void;
  createInitialConversation?: boolean;
}

export function useCreateTaskCallback({
  selectedProjectId,
  state,
  initialConversation,
  navigate,
  onCreated,
  createInitialConversation = true,
}: UseCreateTaskCallbackParams): { handleCreateTask: () => void; canCreate: boolean } {
  const canCreate = !!selectedProjectId && state.isValid;

  const handleCreateTask = useCallback(() => {
    if (!selectedProjectId) return;
    const taskManager = getTaskManagerStore(selectedProjectId);
    if (!taskManager) return;

    const id = crypto.randomUUID();
    void taskManager
      .createTask({
        id,
        projectId: selectedProjectId,
        taskConfig: {
          version: '1',
          name: state.taskName.effectiveTaskName,
          linkedIssue: state.linkedType === 'issue' ? (state.linkedIssue ?? undefined) : undefined,
          initialStatus: deriveInitialStatus(state.linkedType, state.linkedPR),
          initialConversation: createInitialConversation
            ? buildInitialConversation(initialConversation)
            : undefined,
        },
        workspaceConfig: state.workspaceConfig.resolvedConfig,
      })
      .catch((e) => log.error('create task failed', e));

    navigate(taskViewDef({ projectId: selectedProjectId, taskId: id }));
    onCreated();
  }, [
    selectedProjectId,
    state,
    initialConversation,
    createInitialConversation,
    navigate,
    onCreated,
  ]);

  return { handleCreateTask, canCreate };
}
