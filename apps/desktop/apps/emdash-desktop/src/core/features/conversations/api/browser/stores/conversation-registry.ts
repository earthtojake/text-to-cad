import type { SerializedHostRef } from '@emdash/core/primitives/host/api';
import { ConversationManagerStore } from '@core/features/conversations/api/browser/conversation-manager';
import { getProjectHostAccess } from '@core/features/projects/api/browser/stores/project-selectors';
import type { Conversation } from '@core/primitives/conversations/api';

export class ConversationRegistry {
  private readonly entries = new Map<string, ConversationManagerStore>();

  acquire(
    taskId: string,
    projectId: string,
    sessionHost: () => SerializedHostRef,
    preloaded?: Conversation[]
  ): ConversationManagerStore {
    const existing = this.entries.get(taskId);
    if (existing) return existing;
    const store = new ConversationManagerStore(
      projectId,
      taskId,
      preloaded,
      sessionHost,
      getProjectHostAccess(projectId)
    );
    this.entries.set(taskId, store);
    return store;
  }

  get(taskId: string): ConversationManagerStore | undefined {
    return this.entries.get(taskId);
  }

  release(taskId: string): void {
    const store = this.entries.get(taskId);
    if (!store) return;
    store.dispose();
    this.entries.delete(taskId);
  }
}

export const conversationRegistry = new ConversationRegistry();
