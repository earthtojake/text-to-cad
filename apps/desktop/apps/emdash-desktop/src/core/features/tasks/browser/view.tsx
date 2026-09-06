import { observer } from 'mobx-react-lite';
import { useEffect, type ReactNode } from 'react';
import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import { projectViewDef } from '@core/features/projects/contributions/views';
import {
  getTaskManagerStore,
  getTaskStore,
  taskHostActionAvailability,
  taskViewKind,
} from '@core/features/tasks/api/browser/task-state/task-selectors';
import { TaskViewWrapper } from '@core/features/tasks/contributions/browser/task-view-context';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { getTaskComposition } from '@core/features/workbench/api/browser/task-composition-selectors';
import { homeViewDef } from '@core/features/workbench/contributions/views';
import { defineViewRuntime } from '@core/primitives/views/react';
import { TaskMainPanel, TaskViewLoadingState } from './main-panel';
import { TaskScope } from './task-scope';
import { TaskTitlebar } from './task-titlebar';

const TaskViewWrapperWithProviders = observer(function TaskViewWrapperWithProviders({
  children,
  projectId,
  taskId,
}: {
  children: ReactNode;
  projectId: string;
  taskId: string;
}) {
  const taskStore = getTaskStore(projectId, taskId);
  const kind = taskViewKind(taskStore, projectId);
  const hostAction = taskHostActionAvailability(projectId);

  // Auto-provision when the task view is rendered with an idle task — covers
  // session restore where the task wasn't in openTaskIds, direct navigation,
  // and any other path that lands on the task view before provisioning runs.
  useEffect(() => {
    if (kind !== 'idle' || hostAction.kind !== 'enabled') return;
    if (taskStore && 'archivedAt' in taskStore.data && taskStore.data.archivedAt) return;

    getTaskManagerStore(projectId)
      ?.provisionTask(taskId)
      .catch(() => {});
  }, [hostAction.kind, kind, projectId, taskId, taskStore]);

  // Single hydration gate for the task view (spec §Hydration gating): nothing
  // below this boundary may paint persisted view state (titlebar chrome
  // toggles, sidebar, pane layout) before the memento space has hydrated.
  const composition = getTaskComposition(projectId, taskId);
  if (composition && !composition.space.isHydrated) {
    return (
      <div className="flex h-full flex-col bg-background text-foreground">
        <TaskViewLoadingState />
      </div>
    );
  }

  return (
    <TaskViewWrapper projectId={projectId} taskId={taskId}>
      <TaskScope projectId={projectId} taskId={taskId}>
        {children}
      </TaskScope>
    </TaskViewWrapper>
  );
});

export const taskViewRuntime = defineViewRuntime(taskViewDef, {
  slots: {
    wrap: TaskViewWrapperWithProviders,
    titlebar: TaskTitlebar,
    main: TaskMainPanel,
  },
  resolve: ({ projectId, taskId }) => {
    if (
      !getProjectManagerStore().projects.has(projectId) &&
      !getProjectManagerStore().pendingCreationIds.has(projectId)
    ) {
      return { kind: 'redirect', ref: homeViewDef() };
    }
    const taskManager = getTaskManagerStore(projectId);
    if (taskManager && !taskManager.tasks.has(taskId)) {
      return { kind: 'redirect', ref: projectViewDef({ projectId }) };
    }
    return { kind: 'ok' };
  },
});
