import { ListPopoverCard } from '@emdash/ui/react/components';
import { CollectionToolbar, CollectionView, SortSelect } from '@emdash/ui/react/patterns';
import { Button, ToggleGroup } from '@emdash/ui/react/primitives';
import { RotateCcw, Trash2, X } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useLayoutEffect, useState } from 'react';
import { getProjectViewStore } from '@core/features/projects/api/browser/stores/project-selectors';
import type { TaskViewStore } from '@core/features/projects/browser/stores/project-view';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { deleteSelectedTasks } from '@core/features/tasks/api/browser/delete-selected-tasks';
import type { TaskManagerStore } from '@core/features/tasks/api/browser/stores/task-manager';
import { getTaskManagerStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { taskListScope } from '@core/features/tasks/contributions/scopes';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { newChatDraftView } from '@core/features/workbench/contributions/views';
import { useSearchFocusHotkeys } from '@core/primitives/keybindings/browser';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';
import {
  useCurrentViewParams,
  useNavigate,
} from '@core/primitives/navigation/browser/navigation-hooks';
import { disabled, enabled, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { useViewScope, ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';
import { TaskListEmptyState } from './task-list-empty-state';
import {
  createTaskListView,
  type ReadyTask,
  type TaskListTab,
  type TaskListViewModel,
} from './task-list-model';
import { TaskRow } from './task-row';

/** The tasks this surface lists: registered, and not automation runs. */
function listedTasks(taskManager: TaskManagerStore): ReadyTask[] {
  return Array.from(taskManager.tasks.values()).filter(
    (t): t is ReadyTask => t.state !== 'unregistered' && t.data.type !== 'automation-run'
  );
}

const TasksTabs = observer(function TasksTabs({
  view,
  taskView,
  taskManager,
}: {
  view: TaskListViewModel;
  taskView: TaskViewStore;
  taskManager: TaskManagerStore;
}) {
  const filter = view.useFilter();
  const allTasks = listedTasks(taskManager);
  const activeCount = allTasks.filter((t) => !t.data.archivedAt).length;
  const archivedCount = allTasks.length - activeCount;

  return (
    <ToggleGroup.Root
      multiple={false}
      value={[taskView.tab]}
      onValueChange={([value]) => {
        if (!value) return;
        const tab = value as TaskListTab;
        // The memento remembers the tab across sessions; the filter shows it now.
        taskView.setTab(tab);
        filter.set({ tab });
      }}
    >
      <ToggleGroup.Item value="active">Active ({activeCount})</ToggleGroup.Item>
      <ToggleGroup.Item value="archived">Archived ({archivedCount})</ToggleGroup.Item>
    </ToggleGroup.Root>
  );
});

const TasksToolbar = observer(function TasksToolbar({
  view,
  taskView,
}: {
  view: TaskListViewModel;
  taskView: TaskViewStore;
}) {
  const searchRef = useSearchFocusHotkeys();
  const search = view.useSearch();
  const sort = view.useSort();

  return (
    <CollectionToolbar
      ref={searchRef}
      searchValue={search.query}
      onSearchValueChange={search.setQuery}
      searchPlaceholder="Search chats…"
      actions={
        <SortSelect
          sort={{
            ...sort,
            // Persist the chosen sort in the project memento alongside the view.
            setKey: (key) => {
              sort.setKey(key);
              taskView.setSortBy(key);
            },
          }}
        />
      }
    />
  );
});

const TasksSelectionBar = observer(function TasksSelectionBar({
  taskView,
  taskManager,
  projectId,
}: {
  taskView: TaskViewStore;
  taskManager: TaskManagerStore;
  projectId: string;
}) {
  if (taskView.count === 0) return null;
  const bulkApply = (apply: (id: string) => void) => {
    [...taskView.selectedIds].forEach(apply);
    taskView.clear();
  };

  return (
    <ListPopoverCard className="justify-between">
      <span className="whitespace-nowrap text-foreground-muted">
        {taskView.count} {taskView.count === 1 ? 'chat' : 'chats'} selected
      </span>
      <div className="flex items-center gap-2">
        {taskView.tab === 'archived' && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => bulkApply((id) => void taskManager.restoreTask(id))}
          >
            <RotateCcw className="size-3.5" />
            Restore
          </Button>
        )}
        <Button variant="destructive" size="sm" onClick={() => void deleteSelectedTasks(projectId)}>
          <Trash2 className="size-3.5" />
          Delete <BoundShortcut command="task.deleteSelected" variant="keycaps" />
        </Button>
        <Button
          variant="ghost"
          size="xs"
          icon
          onClick={() => taskView.clear()}
          aria-label="Clear selection"
        >
          <X className="size-3.5" />
        </Button>
      </div>
    </ListPopoverCard>
  );
});

const TaskListContent = observer(function TaskListContent({
  projectId,
  taskManager,
  taskView,
}: {
  projectId: string;
  taskManager: TaskManagerStore;
  taskView: TaskViewStore;
}) {
  const { navigate } = useNavigate();

  const [view] = useState(() =>
    createTaskListView({
      getTasks: () => listedTasks(taskManager),
      initialTab: taskView.tab,
      initialSortBy: taskView.sortBy,
      selection: taskView,
    })
  );

  // Shift-ranges follow the list's visible order; wire it in before any clicks.
  useLayoutEffect(() => {
    taskView.attachOrderedIds(() => view.store.orderedIds);
  }, [taskView, view]);

  return (
    <view.Root>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 pb-3">
        <TasksTabs view={view} taskView={taskView} taskManager={taskManager} />
        <Button
          variant="primary"
          aria-label="Create chat"
          onClick={() => navigate(newChatDraftView(projectId))}
        >
          New chat <BoundShortcut command="app.newTask" variant="keycaps" />
        </Button>
      </div>
      <CollectionView
        view={view}
        renderRow={(task) => <TaskRow task={task} view={view} />}
        toolbar={<TasksToolbar view={view} taskView={taskView} />}
        footer={
          <TasksSelectionBar taskView={taskView} taskManager={taskManager} projectId={projectId} />
        }
        onItemClick={(task) => {
          if (task.data.archivedAt) return;
          void taskManager.provisionTask(task.data.id);
          navigate(taskViewDef({ projectId, taskId: task.data.id }));
        }}
        emptySlot={
          taskView.tab === 'active' ? (
            <TaskListEmptyState projectId={projectId} />
          ) : (
            <div className="flex h-full items-center justify-center p-6 text-sm text-foreground-muted">
              No archived chats
            </div>
          )
        }
      />
    </view.Root>
  );
});

export const TaskList = observer(function TaskList() {
  const {
    params: { projectId },
  } = useCurrentViewParams(projectViewDef);
  const taskManager = getTaskManagerStore(projectId);
  const taskView = getProjectViewStore(projectId)?.taskView ?? null;

  const implementation = {
    'task.deleteSelected': () => ({
      availability: () =>
        taskView && taskView.count > 0 ? enabled : disabled('Select one or more chats'),
      execute: () => {
        void deleteSelectedTasks(projectId);
      },
    }),
  } satisfies ViewScopeImpl<typeof taskListScope>;
  const { attachRef, instance } = useViewScope(taskListScope({ projectId }), implementation);

  if (!taskManager || !taskView) return null;

  return (
    <ViewScopeInstanceProvider instance={instance}>
      <div
        ref={attachRef}
        tabIndex={-1}
        className="relative flex h-full min-h-0 w-full flex-col outline-none"
        onPointerDownCapture={(event) => event.currentTarget.focus({ preventScroll: true })}
      >
        <TaskListContent
          key={projectId}
          projectId={projectId}
          taskManager={taskManager}
          taskView={taskView}
        />
      </div>
    </ViewScopeInstanceProvider>
  );
});
