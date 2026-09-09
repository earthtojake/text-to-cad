import { createConversationModal } from '../browser/create-conversation-modal';

export const conversationsBrowserContributions = {
  modalDefs: [createConversationModal],
} as const;
