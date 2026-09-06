import type { ConversationType } from '@core/primitives/conversations/api';

/**
 * Maps a conversation type to the corresponding tab kind so callers
 * don't have to branch on 'acp' vs 'pty' inline.
 */
export function conversationTabKind(
  type: ConversationType | undefined
): 'conversation' | 'acp-chat' {
  return type === 'acp' ? 'acp-chat' : 'conversation';
}
