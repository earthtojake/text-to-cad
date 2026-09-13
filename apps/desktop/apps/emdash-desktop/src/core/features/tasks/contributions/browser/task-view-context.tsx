import { observer } from 'mobx-react-lite';
import { createContext, useContext, type ReactNode } from 'react';
import { ProjectViewWrapper } from '@core/features/projects/contributions/browser/project-view-wrapper';
import {
  getTaskStore,
  taskViewKind,
  type TaskViewKind,
} from '@core/features/tasks/api/browser/task-state/task-selectors';
import { taskSubject } from '@core/features/tasks/contributions/subject';
import { SubjectProvider } from '@core/primitives/mementos/react';

interface TaskViewContext {
  projectId: string;
  taskId: string;
}

const TaskViewContext = createContext<TaskViewContext | null>(null);

export const TaskViewWrapper = observer(function TaskViewWrapper({
  children,
  projectId,
  taskId,
}: {
  children: ReactNode;
  projectId: string;
  taskId: string;
}) {
  return (
    <ProjectViewWrapper projectId={projectId}>
      <SubjectProvider subject={taskSubject({ taskId })}>
        <TaskViewContext.Provider value={{ projectId, taskId }}>
          {children}
        </TaskViewContext.Provider>
      </SubjectProvider>
    </ProjectViewWrapper>
  );
});

export function useTaskViewContext(): TaskViewContext {
  const context = useContext(TaskViewContext);
  if (!context) {
    throw new Error('useTaskViewContext must be used within a TaskViewContextProvider');
  }
  return context;
}

export function useTaskViewKind(): TaskViewKind {
  const { projectId, taskId } = useTaskViewContext();
  return taskViewKind(getTaskStore(projectId, taskId), projectId);
}
