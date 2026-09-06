import type {
  ChatView,
  ChatViewCommandId,
} from '@core/features/conversations/api/browser/chat/chat-transcript';

type ChatShortcutEvent = Pick<
  KeyboardEvent,
  'key' | 'metaKey' | 'ctrlKey' | 'altKey' | 'shiftKey' | 'isComposing'
>;

export function chatViewCommandForShortcut(event: ChatShortcutEvent): ChatViewCommandId | null {
  if (event.isComposing || event.altKey || event.shiftKey || (!event.metaKey && !event.ctrlKey)) {
    return null;
  }

  switch (event.key) {
    case 'ArrowUp':
      return 'chat.scrollToTop';
    case 'ArrowDown':
      return 'chat.scrollToBottom';
    default:
      return null;
  }
}

export function executeChatViewCommand(
  view: ChatView | null,
  commandId: ChatViewCommandId
): boolean {
  if (!view) return false;

  switch (commandId) {
    case 'chat.scrollToTop':
      view.scrollToTop({ behavior: 'smooth' });
      return true;
    case 'chat.scrollToBottom':
      view.scrollToBottom({ behavior: 'smooth' });
      return true;
  }
}
