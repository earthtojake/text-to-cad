import { conversationManagerStoreToken } from '@core/features/conversations/contributions/browser/task-stores';
import { gitRepositoryStoreToken } from '@core/features/source-control/contributions/browser/project-stores';
import type { TaskScopedStoreContext } from '@core/features/tasks/contributions/browser/task-stores';
import { terminalManagerStoreToken } from '@core/features/terminals/contributions/browser/task-stores';
import { TaskComposition } from '@core/features/workbench/api/browser/task-composition';
import { TaskCompositionHandle } from '@core/features/workbench/api/browser/task-composition-handle';
import { taskCompositionHandleStoreToken } from '@core/features/workbench/contributions/browser/task-store-tokens';
import {
  contributeScopedStore,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';

export const workbenchTaskStoreContributions: readonly ScopedStoreContribution<TaskScopedStoreContext>[] =
  [
    contributeScopedStore({
      token: taskCompositionHandleStoreToken,
      create: ({ projectId, taskId, task, projectStores }, stores) => {
        const terminals = stores.get(terminalManagerStoreToken);
        const conversations = stores.get(conversationManagerStoreToken);
        const gitRepository = projectStores.get(gitRepositoryStoreToken);
        return new TaskCompositionHandle(
          task,
          (workspaceId) =>
            new TaskComposition(
              projectId,
              taskId,
              workspaceId,
              task,
              terminals,
              conversations,
              gitRepository
            )
        );
      },
      ready: (handle) => handle.ready(),
      activate: (handle) => handle.activate(),
      dispose: (handle) => handle.dispose(),
    }),
  ];
