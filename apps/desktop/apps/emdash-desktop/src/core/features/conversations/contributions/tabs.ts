import { acpChatTabProvider } from '../browser/acp/acp-chat-tab-provider';
import { conversationTabProvider } from '../browser/conversation-tab-provider';

export const conversationTaskTabContributions = [
  conversationTabProvider,
  acpChatTabProvider,
] as const;
