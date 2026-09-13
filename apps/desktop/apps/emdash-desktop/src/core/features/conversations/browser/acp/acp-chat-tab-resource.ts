import { conversationRegistry } from '@core/features/conversations/api/browser/stores/conversation-registry';
import type { TabResource } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import type { AcpChatStore } from './acp-chat-store';

/**
 * Domain resource for a single open ACP-chat tab.
 *
 * Thin wrapper over AcpChatStore that implements TabResource.
 * The store's lifecycle is managed by AcpChatResourceManager (retain/release).
 * This resource simply exposes the store and bootstraps it on activate.
 */
export class AcpChatTabResource implements TabResource {
  readonly store: AcpChatStore;

  constructor(store: AcpChatStore) {
    this.store = store;
  }

  dispose(): void {
    // AcpChatResourceManager owns the store lifetime.
    // The manager disposes the store after grace when the last tab is closed.
  }

  onActivate(): void {
    // Lazy bootstrap: safe to call repeatedly (idempotent).
    this.store.bootstrap();
    // Mirror ConversationTabResource: clear the notification indicator when
    // the user opens this tab.
    const conversation = conversationRegistry
      .get(this.store.taskId)
      ?.conversations.get(this.store.conversationId);
    if (conversation && !conversation.seen) conversation.markSeen();
  }

  rename(name: string): void {
    void conversationRegistry
      .get(this.store.taskId)
      ?.renameConversation(this.store.conversationId, name);
  }
}
