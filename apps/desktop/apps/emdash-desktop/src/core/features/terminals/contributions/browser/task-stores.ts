import type { TaskScopedStoreContext } from '@core/features/tasks/contributions/browser/task-stores';
import { terminalRegistry } from '@core/features/terminals/api/browser/stores/terminal-registry';
import type { TerminalManagerStore } from '@core/features/terminals/api/browser/task-terminal/terminal-manager';
import {
  contributeScopedStore,
  scopedStoreToken,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';

export const terminalManagerStoreToken =
  scopedStoreToken<TerminalManagerStore>('terminals.manager');

export const terminalTaskStoreContributions: readonly ScopedStoreContribution<TaskScopedStoreContext>[] =
  [
    contributeScopedStore({
      token: terminalManagerStoreToken,
      create: ({ projectId, taskId }) => terminalRegistry.acquire(taskId, projectId),
      dispose: (_, { taskId }) => terminalRegistry.release(taskId),
    }),
  ];
