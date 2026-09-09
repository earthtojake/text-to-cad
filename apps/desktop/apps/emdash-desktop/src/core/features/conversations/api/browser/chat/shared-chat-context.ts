import type { ChatContext } from '@emdash/chat-ui';
import { advertisedCommandProvider } from './advertised-command-provider';
import { chatMentionProvider } from './chat-mention-provider';
import { getChatUiRuntime } from './chat-ui-runtime';

let shared: ChatContext | null = null;

/**
 * Create the process-long ChatContext. Call once from the renderer bootstrap
 * (main.tsx) so the context's font-load hook fires at startup rather than on
 * first conversation open.
 *
 * ChatContext is a global singleton (theme, shared caches, measureEpoch).
 * Per-conversation state lives in ChatState, which is created separately.
 */
export function initSharedChatContext(): ChatContext {
  if (!shared) {
    shared = getChatUiRuntime().createChatContext({
      mentionProvider: chatMentionProvider,
      commandProvider: advertisedCommandProvider,
    });
  }
  return shared;
}

/**
 * Access the process-long ChatContext. Lazily initializes as a defensive
 * fallback if a consumer runs before bootstrap completes.
 */
export function getSharedChatContext(): ChatContext {
  return shared ?? initSharedChatContext();
}
