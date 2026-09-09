import type { z } from 'zod';
import type { taskViewLocationSchema } from '@core/features/tasks/contributions/views';
import type { NavigationParticipant } from '@core/primitives/navigation/api';

type TaskViewLocation = z.infer<typeof taskViewLocationSchema>;

interface TaskPaneLayout {
  readonly focusedPane: {
    readonly resolvedActiveTabId: string | undefined;
    readonly entries: { has(tabId: string): boolean };
    setActiveTab(tabId: string): void;
  };
}

export class TaskNavigationParticipant implements NavigationParticipant<TaskViewLocation> {
  constructor(private readonly paneLayout: TaskPaneLayout) {}

  captureLocation(): TaskViewLocation | undefined {
    const tabId = this.paneLayout.focusedPane.resolvedActiveTabId;
    return tabId ? { tabId } : undefined;
  }

  restoreLocation({ tabId }: TaskViewLocation): boolean {
    if (!this.paneLayout.focusedPane.entries.has(tabId)) return false;
    this.paneLayout.focusedPane.setActiveTab(tabId);
    return true;
  }
}
