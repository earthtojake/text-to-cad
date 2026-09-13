import { describe, expect, it, vi } from 'vitest';
import {
  readLastCadConversationProvider,
  rememberCadConversationProvider,
} from './cad-conversation-provider';

describe('CAD conversation provider memory', () => {
  it('remembers Claude or Codex per host', () => {
    const setItem = vi.fn();

    rememberCadConversationProvider({ setItem }, 'codex', 'shop-mac');

    expect(setItem).toHaveBeenCalledWith('hardcore:cad:new-chat-agent:shop-mac', 'codex');
  });

  it('ignores unsupported or unavailable stored values', () => {
    expect(readLastCadConversationProvider({ getItem: () => 'opencode' })).toBeUndefined();
    expect(
      readLastCadConversationProvider({
        getItem: () => {
          throw new Error('blocked');
        },
      })
    ).toBeUndefined();
  });
});
