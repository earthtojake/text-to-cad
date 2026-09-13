import { describe, expect, it } from 'vitest';
import { CHAT_VIEW_COMMANDS } from './commands';

describe('CHAT_VIEW_COMMANDS', () => {
  it('exposes stable scroll command ids', () => {
    expect(CHAT_VIEW_COMMANDS.map((command) => command.id)).toEqual([
      'chat.scrollToTop',
      'chat.scrollToBottom',
    ]);
  });
});
