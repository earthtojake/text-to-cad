import { describe, expect, it, vi } from 'vitest';
import type { ChatView } from '@core/features/conversations/api/browser/chat/chat-transcript';
import { chatViewCommandForShortcut, executeChatViewCommand } from './acp-chat-view-commands';

describe('acp chat view commands', () => {
  it('maps host-owned shortcuts to chat command ids', () => {
    expect(
      chatViewCommandForShortcut({
        key: 'ArrowUp',
        metaKey: true,
        ctrlKey: false,
        altKey: false,
        shiftKey: false,
        isComposing: false,
      })
    ).toBe('chat.scrollToTop');
    expect(
      chatViewCommandForShortcut({
        key: 'ArrowDown',
        metaKey: false,
        ctrlKey: true,
        altKey: false,
        shiftKey: false,
        isComposing: false,
      })
    ).toBe('chat.scrollToBottom');
  });

  it('ignores modified or composing shortcut events', () => {
    expect(
      chatViewCommandForShortcut({
        key: 'ArrowDown',
        metaKey: true,
        ctrlKey: false,
        altKey: true,
        shiftKey: false,
        isComposing: false,
      })
    ).toBeNull();
    expect(
      chatViewCommandForShortcut({
        key: 'ArrowDown',
        metaKey: true,
        ctrlKey: false,
        altKey: false,
        shiftKey: false,
        isComposing: true,
      })
    ).toBeNull();
  });

  it('executes scroll commands against the active view', () => {
    const view = {
      scrollToTop: vi.fn(),
      scrollToBottom: vi.fn(),
    } as unknown as ChatView;

    expect(executeChatViewCommand(view, 'chat.scrollToTop')).toBe(true);
    expect(view.scrollToTop).toHaveBeenCalledWith({ behavior: 'smooth' });

    expect(executeChatViewCommand(view, 'chat.scrollToBottom')).toBe(true);
    expect(view.scrollToBottom).toHaveBeenCalledWith({ behavior: 'smooth' });
  });
});
