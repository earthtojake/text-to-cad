import type { SerializedHostRef } from '@emdash/core/primitives/host/api';
import type { ConversationsRuntimeBroker } from '@core/features/conversations/api/runtime-adapter';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import type {
  CompensationRunner,
  ConversationWorkspaceIdentityResolver,
} from './createConversation';
import { createConversation } from './createConversation';
import { dehydrateConversation } from './dehydrateConversation';
import { deleteHostConversation } from './delete-host-conversation';
import { deleteConversation } from './deleteConversation';
import { getConversations } from './getConversations';
import { getConversationsForProject } from './getConversationsForProject';
import { getConversationsForTask } from './getConversationsForTask';
import { hydrateConversation } from './hydrateConversation';
import { linkConversationToTask } from './link-conversation-to-task';
import { listHostConversations } from './list-host-conversations';
import { markConversationSeen } from './markConversationSeen';
import { renameConversation } from './renameConversation';

export function createConversationOperations(dependencies: {
  db: AppDb;
  telemetry: TelemetryService;
  taskSessions: Pick<TaskSessionManager, 'getTask'>;
  withCompensation: CompensationRunner;
  runtimes: ConversationsRuntimeBroker;
  hostIsReachable: (hostRef: SerializedHostRef) => boolean;
  workspaceIdentity: ConversationWorkspaceIdentityResolver;
}) {
  const { db, telemetry, withCompensation } = dependencies;
  return {
    getConversations: () => getConversations(db),
    createConversation: (params: Parameters<typeof createConversation>[0]) =>
      createConversation(params, {
        db,
        taskSessions: dependencies.taskSessions,
        telemetry,
        withCompensation,
        runtimes: dependencies.runtimes,
        hostIsReachable: dependencies.hostIsReachable,
        workspaceIdentity: dependencies.workspaceIdentity,
      }),
    deleteConversation: (projectId: string, taskId: string, conversationId: string) =>
      deleteConversation(db, dependencies.runtimes, projectId, taskId, conversationId, telemetry),
    hydrateConversation: (
      projectId: string,
      taskId: string,
      conversationId: string,
      initialSize?: { cols: number; rows: number }
    ) =>
      hydrateConversation(
        db,
        dependencies.taskSessions,
        projectId,
        taskId,
        conversationId,
        telemetry,
        initialSize
      ),
    dehydrateConversation: (projectId: string, taskId: string, conversationId: string) =>
      dehydrateConversation(db, dependencies.taskSessions, projectId, taskId, conversationId),
    renameConversation: (conversationId: string, name: string) =>
      renameConversation(
        {
          db,
          runtimes: dependencies.runtimes,
          hostIsReachable: dependencies.hostIsReachable,
        },
        conversationId,
        name
      ),
    getConversationsForTask: (projectId: string, taskId: string) =>
      getConversationsForTask(db, projectId, taskId),
    getConversationsForProject: (projectId: string) => getConversationsForProject(db, projectId),
    markConversationSeen: (conversationId: string) => markConversationSeen(db, conversationId),
    listHostConversations: (scope: Parameters<typeof listHostConversations>[1]) =>
      listHostConversations(db, scope),
    linkConversationToTask: (input: Parameters<typeof linkConversationToTask>[1]) =>
      linkConversationToTask(db, input),
    deleteHostConversation: (conversationId: string) =>
      deleteHostConversation(db, dependencies.runtimes, conversationId, telemetry),
  };
}
