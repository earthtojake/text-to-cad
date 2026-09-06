import { conversationTaskStoreContributions } from '@core/features/conversations/contributions/browser/task-stores';
import { sourceControlTaskStoreContributions } from '@core/features/source-control/contributions/browser/task-stores';
import type { TaskScopedStoreContext } from '@core/features/tasks/contributions/browser/task-stores';
import { terminalTaskStoreContributions } from '@core/features/terminals/contributions/browser/task-stores';
import { workbenchTaskStoreContributions } from '@core/features/workbench/browser/contributions/task-stores';
import type { ScopedStoreContribution } from '@core/primitives/scoped-stores/browser';

export const taskStoreContributions: readonly ScopedStoreContribution<TaskScopedStoreContext>[] = [
  ...conversationTaskStoreContributions,
  ...sourceControlTaskStoreContributions,
  ...terminalTaskStoreContributions,
  ...workbenchTaskStoreContributions,
];
