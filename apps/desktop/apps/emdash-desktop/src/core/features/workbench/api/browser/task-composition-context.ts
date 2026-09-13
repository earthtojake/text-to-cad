import type { ConversationManagerStore } from '@core/features/conversations/api/browser/conversation-manager';
import { getConversationsForTask } from '@core/features/conversations/api/browser/conversation-selectors';
import { getTaskStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import type { TerminalManagerStore } from '@core/features/terminals/api/browser/task-terminal/terminal-manager';
import { getTerminalsForTask } from '@core/features/terminals/api/browser/terminal-selectors';
import type { TaskComposition } from '@core/features/workbench/api/browser/task-composition';
import type { WorkspaceStore } from '@core/features/workspaces/api/browser/stores/workspace';
import { getTaskComposition, getTaskWorkspace } from './task-composition-selectors';

export function useTaskComposition(): TaskComposition {
  const { projectId, taskId } = useTaskViewContext();
  const composition = getTaskComposition(projectId, taskId);
  if (!composition) throw new Error('useTaskComposition: task is not registered');
  return composition;
}

export function useWorkspace(): WorkspaceStore {
  const { projectId, taskId } = useTaskViewContext();
  const workspace = getTaskWorkspace(projectId, taskId);
  if (!workspace) throw new Error('useWorkspace: task is not provisioned');
  return workspace;
}

export function useWorkspaceId(): string {
  const { projectId, taskId } = useTaskViewContext();
  const workspaceId = getTaskStore(projectId, taskId)?.workspaceId;
  if (!workspaceId) throw new Error('useWorkspaceId: task has no workspace');
  return workspaceId;
}

export function useConversations(): ConversationManagerStore {
  const { taskId } = useTaskViewContext();
  const manager = getConversationsForTask(taskId);
  if (!manager) throw new Error('useConversations: task is not registered');
  return manager;
}

export function useTerminals(): TerminalManagerStore {
  const { taskId } = useTaskViewContext();
  const manager = getTerminalsForTask(taskId);
  if (!manager) throw new Error('useTerminals: task is not registered');
  return manager;
}
