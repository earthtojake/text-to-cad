import { taskViewDef } from '@core/features/tasks/contributions/views';
import {
  useViewParams,
  useWorkspaceSlots,
} from '@core/primitives/navigation/browser/navigation-hooks';

export function useIsActiveTask(taskId: string): boolean {
  const { currentView } = useWorkspaceSlots();
  const params = useViewParams(taskViewDef);
  return currentView === 'task' && params?.taskId === taskId;
}
