import { getProjectViewStore } from '@core/features/projects/api/browser/stores/project-selectors';
import { getTaskManagerStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { openModal } from '@core/manifests/browser/modal-api';

export function selectedTaskCount(projectId: string | undefined): number {
  if (!projectId) return 0;
  return getProjectViewStore(projectId)?.taskView.count ?? 0;
}

export async function deleteSelectedTasks(projectId: string): Promise<void> {
  const taskManager = getTaskManagerStore(projectId);
  const taskView = getProjectViewStore(projectId)?.taskView;
  if (!taskManager || !taskView || taskView.selectedIds.size === 0) return;

  const selectedTasks = [...taskView.selectedIds].flatMap((id) => {
    const task = taskManager.tasks.get(id);
    return task ? [{ taskId: task.data.id, taskName: task.data.name }] : [];
  });
  if (selectedTasks.length === 0) return;

  const outcome = await openModal('deleteTaskModal', {
    projectId,
    tasks: selectedTasks,
  });
  if (!outcome.success) return;

  const { deleteWorktree, deleteBranch, deleteConversations } = outcome.data;
  await taskManager.deleteTasks([...taskView.selectedIds], {
    deleteWorktree,
    deleteBranch,
    deleteConversations,
  });
  taskView.clear();
}
