import { TaskList } from '@core/features/projects/browser/components/task-view/task-list';

export function ActiveProject() {
  return (
    <div className="flex h-[calc(100vh-12rem)] min-h-96 w-full flex-col">
      <TaskList />
    </div>
  );
}
