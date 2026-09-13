import { openFileInTaskEditor } from '@core/features/editor/api/browser/open-file-in-file-editor';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import type { SearchItem } from '@core/primitives/search/api';
import type { ViewRef } from '@core/primitives/views/api';

export function openCommandPaletteFile(
  item: Pick<SearchItem, 'id' | 'projectId' | 'taskId'>,
  dismiss: () => void,
  navigate: (ref: ViewRef) => void
): void {
  if (!item.projectId || !item.taskId) return;

  void openFileInTaskEditor(item.projectId, item.taskId, item.id);
  dismiss();
  navigate(taskViewDef({ projectId: item.projectId, taskId: item.taskId }));
}
