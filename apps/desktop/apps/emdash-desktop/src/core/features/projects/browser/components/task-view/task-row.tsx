import { AgentStatus } from '@emdash/ui/react/components';
import { Checkbox, RelativeTime } from '@emdash/ui/react/primitives';
import { MessageSquare, MoreHorizontal } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { taskAgentStatus } from '@core/features/conversations/api/browser/conversation-selectors';
import { getTaskManagerStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import {
  TaskContextMenu,
  TaskDropdownMenu,
} from '@core/features/tasks/contributions/browser/task-context-menu';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import { cn } from '@core/primitives/styling/browser/cn';
import { type ReadyTask, type TaskListViewModel } from './task-list-model';

/**
 * Row content for the project task list. The CollectionView shell owns row
 * click (navigation) and modifier-click selection; this component renders the
 * content, the hover-revealed checkbox, and the context menu.
 */
export const TaskRow = observer(function TaskRow({
  task,
  view,
}: {
  task: ReadyTask;
  view: TaskListViewModel;
}) {
  const { id } = view.useItem();
  const selection = view.useSelection();
  const openRename = useOpenModal('renameTaskModal');
  const openDeleteTask = useOpenModal('deleteTaskModal');
  const taskManager = getTaskManagerStore(task.data.projectId);

  const handleRestore = () => void taskManager?.restoreTask(task.data.id);
  const handleArchive = () => void taskManager?.archiveTask(task.data.id);
  const handleDelete = () => {
    void openDeleteTask({
      projectId: task.data.projectId,
      tasks: [{ taskId: task.data.id, taskName: task.data.name }],
    }).then((outcome) => {
      if (!outcome.success) return;
      const { deleteWorktree, deleteBranch, deleteConversations } = outcome.data;
      void taskManager?.deleteTasks([task.data.id], {
        deleteWorktree,
        deleteBranch,
        deleteConversations,
      });
    });
  };
  const handleRename = () => {
    void openRename({
      projectId: task.data.projectId,
      taskId: task.data.id,
      currentName: task.data.name,
    });
  };
  const isArchived = Boolean(task.data.archivedAt);
  const isSelected = selection.isSelected(id);
  const canPin = task.state !== 'unregistered';
  const agentAttention = taskAgentStatus(task);
  return (
    <TaskContextMenu
      isPinned={task.data.isPinned}
      canPin={canPin}
      isArchived={isArchived}
      branchName={undefined}
      onPin={() => void task.setPinned(true)}
      onUnpin={() => void task.setPinned(false)}
      onRename={handleRename}
      onArchive={!isArchived && task.state !== 'unregistered' ? handleArchive : undefined}
      onRestore={handleRestore}
      onDelete={handleDelete}
    >
      <div className="group flex w-full items-center gap-2">
        {/*
          Mouse clicks land on the wrapper (the checkbox is pointer-events-none)
          so the real event's modifier keys reach `toggle`; keyboard activation
          reaches the focusable checkbox itself and toggles via onCheckedChange.
          The target check keeps the keyboard path from double-toggling through
          the synthetic click that bubbles up.
        */}
        <span
          onClick={(event) => {
            event.stopPropagation();
            if (event.target === event.currentTarget) selection.toggle(id, event);
          }}
          className={cn(
            'inline-flex cursor-pointer transition-opacity focus-within:opacity-100',
            isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
          )}
        >
          <Checkbox
            checked={isSelected}
            onCheckedChange={() => selection.toggle(id)}
            className="pointer-events-none"
            aria-label="Select chat"
          />
        </span>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-background-1 text-foreground-muted">
            <MessageSquare className="size-3.5" />
          </span>
          <span className="min-w-0 truncate text-left text-sm">{task.data.name}</span>
        </div>
        <div
          className={cn(
            'relative flex min-h-7 min-w-8 shrink-0 items-center justify-end',
            agentAttention ? 'justify-end' : 'justify-middle'
          )}
        >
          <span className="transition-opacity group-focus-within:opacity-0 group-hover:opacity-0">
            {agentAttention ? (
              <AgentStatus status={agentAttention} tooltip />
            ) : (
              <span className="flex items-center gap-1.5 text-xs text-foreground-passive">
                Updated
                <RelativeTime value={task.data.updatedAt} className="font-sans text-xs" compact />
              </span>
            )}
          </span>
          <TaskDropdownMenu
            isPinned={task.data.isPinned}
            canPin={canPin}
            isArchived={isArchived}
            branchName={undefined}
            onPin={() => void task.setPinned(true)}
            onUnpin={() => void task.setPinned(false)}
            onRename={handleRename}
            onArchive={!isArchived && task.state !== 'unregistered' ? handleArchive : undefined}
            onRestore={isArchived ? handleRestore : undefined}
            onDelete={handleDelete}
            trigger={
              <button
                type="button"
                className="absolute right-0 flex size-7 items-center justify-center rounded-md text-foreground-muted opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 hover:bg-background-2 hover:text-foreground focus-visible:opacity-100 data-[popup-open]:opacity-100"
                aria-label={`More actions for ${task.data.name || 'chat'}`}
                title="Chat actions"
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => event.stopPropagation()}
              >
                <MoreHorizontal className="size-4" />
              </button>
            }
          />
        </div>
      </div>
    </TaskContextMenu>
  );
});
