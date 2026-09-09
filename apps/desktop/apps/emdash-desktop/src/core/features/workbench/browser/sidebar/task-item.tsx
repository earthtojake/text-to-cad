import { toast } from '@emdash/ui/react/primitives';
import { MoreHorizontal } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { projectViewDef } from '@core/features/projects/contributions/views';
import {
  getTaskManagerStore,
  getTaskStore,
} from '@core/features/tasks/api/browser/task-state/task-selectors';
import {
  TaskContextMenu,
  TaskDropdownMenu,
} from '@core/features/tasks/contributions/browser/task-context-menu';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { getTaskWorkspace } from '@core/features/workbench/api/browser/task-composition-selectors';
import { TaskSidebarTrailingSlot } from '@core/features/workbench/browser/sidebar/task-sidebar-agent-status';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import {
  useNavigate,
  useViewParams,
  useWorkspaceSlots,
} from '@core/primitives/navigation/browser/navigation-hooks';
import { cn } from '@core/primitives/styling/browser/cn';
import { SidebarItemMiniButton, SidebarMenuAction, SidebarMenuRow } from './sidebar-primitives';

interface SidebarTaskItemProps {
  taskId: string;
  projectId: string;
  /** Pinned strip uses tighter padding than tasks nested under a project. */
  rowVariant?: 'underProject' | 'pinned';
}

export const SidebarTaskItem = observer(function SidebarTaskItem({
  taskId,
  projectId,
  rowVariant = 'underProject',
}: SidebarTaskItemProps) {
  const { navigate } = useNavigate();
  const openRename = useOpenModal('renameTaskModal');
  const openDeleteTask = useOpenModal('deleteTaskModal');

  const { currentView } = useWorkspaceSlots();
  const params = useViewParams(taskViewDef);
  const isActive =
    currentView === 'task' && params?.taskId === taskId && params.projectId === projectId;
  const task = getTaskStore(projectId, taskId)!;
  const taskManager = getTaskManagerStore(projectId);

  const taskName = task.data.name;

  const handleProvision = () => {
    if (task.state !== 'unprovisioned' || task.phase !== 'idle') return;
    void taskManager?.provisionTask(taskId);
  };

  const openTask = () => {
    handleProvision();
    navigate(taskViewDef({ projectId, taskId }));
  };

  const handleRename = () => {
    void openRename({ projectId, taskId, currentName: taskName });
  };

  const handleDelete = () => {
    void openDeleteTask({
      projectId,
      tasks: [{ taskId, taskName }],
    }).then((outcome) => {
      if (!outcome.success) return;
      const { deleteWorktree, deleteBranch, deleteConversations } = outcome.data;
      void taskManager?.deleteTasks([taskId], {
        deleteWorktree,
        deleteBranch,
        deleteConversations,
      });
      if (isActive) navigate(projectViewDef({ projectId }));
    });
  };

  const canArchive = task.state !== 'unregistered';
  const handleArchive = () => {
    if (!canArchive) return;
    void taskManager?.archiveTask(taskId).catch(() => toast.error('Could not archive chat'));
  };

  const canPin = task.state !== 'unregistered';
  const workspaceStore = getTaskWorkspace(projectId, taskId);
  const handleReconnect =
    workspaceStore?.connectionState != null ? () => workspaceStore.reconnect() : undefined;

  const taskRow = (
    <TaskContextMenu
      isPinned={task.data.isPinned}
      canPin={canPin}
      isArchived={false}
      branchName={undefined}
      onPin={() => void task.setPinned(true)}
      onUnpin={() => void task.setPinned(false)}
      onRename={handleRename}
      onReconnect={handleReconnect}
      onArchive={canArchive ? handleArchive : undefined}
      onDelete={handleDelete}
    >
      <SidebarMenuRow
        className={cn(
          'group/row flex h-8 items-center justify-between gap-2 px-2 py-1',
          rowVariant === 'pinned' ? 'pl-2' : 'pl-6'
        )}
        isActive={isActive}
        onMouseDown={(event) => event.preventDefault()}
        onClick={openTask}
      >
        <SidebarMenuAction
          aria-label={`Open chat ${taskName || 'chat'}`}
          className="overflow-hidden"
          onClick={(event) => {
            event.stopPropagation();
            openTask();
          }}
        >
          <span
            className={cn(
              'min-w-0 truncate text-left transition-colors',
              task.isBootstrapping && 'text-foreground/40'
            )}
          >
            {taskName}
          </span>
        </SidebarMenuAction>
        <div className="relative ml-auto flex min-h-6 min-w-6 shrink-0 items-center justify-end">
          <span className="transition-opacity group-focus-within/row:opacity-0 group-hover/row:opacity-0">
            <TaskSidebarTrailingSlot task={task} showTimestamp />
          </span>
          <TaskDropdownMenu
            isPinned={task.data.isPinned}
            canPin={canPin}
            isArchived={false}
            branchName={undefined}
            onPin={() => void task.setPinned(true)}
            onUnpin={() => void task.setPinned(false)}
            onRename={handleRename}
            onReconnect={handleReconnect}
            onArchive={canArchive ? handleArchive : undefined}
            onDelete={handleDelete}
            trigger={
              <SidebarItemMiniButton
                type="button"
                className="absolute top-0 right-0 opacity-0 transition-opacity group-focus-within/row:opacity-100 group-hover/row:opacity-100 focus-visible:opacity-100 data-[popup-open]:opacity-100"
                aria-label={`More actions for ${taskName || 'chat'}`}
                title="Chat actions"
                onClick={(event) => event.stopPropagation()}
              >
                <MoreHorizontal className="size-3.5" />
              </SidebarItemMiniButton>
            }
          />
        </div>
      </SidebarMenuRow>
    </TaskContextMenu>
  );

  return taskRow;
});
