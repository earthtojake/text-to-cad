import { log } from '@emdash/shared/logger';
import type { Conversation } from '@core/primitives/conversations/api';
import { HookCore, type Hookable } from '@core/primitives/hooks/api/hookable';

export type ConversationCrudHooks = {
  'conversation:created': (conversation: Conversation) => void | Promise<void>;
  'conversation:renamed': (
    conversationId: string,
    projectId: string,
    taskId: string,
    newTitle: string
  ) => void | Promise<void>;
  'conversation:deleted': (conversationId: string) => void | Promise<void>;
};

class ConversationEvents implements Hookable<ConversationCrudHooks> {
  private readonly _core = new HookCore<ConversationCrudHooks>((name, e) =>
    log.error(`ConversationEvents: ${String(name)} hook error`, { error: e })
  );

  on<K extends keyof ConversationCrudHooks>(name: K, handler: ConversationCrudHooks[K]) {
    return this._core.on(name, handler);
  }

  _emit<K extends keyof ConversationCrudHooks>(
    name: K,
    ...args: Parameters<ConversationCrudHooks[K]>
  ): void {
    this._core.callHookBackground(name, ...args);
  }
}

export const conversationEvents = new ConversationEvents();
