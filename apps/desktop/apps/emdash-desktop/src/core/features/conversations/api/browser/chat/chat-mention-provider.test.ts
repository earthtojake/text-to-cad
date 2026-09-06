import { describe, expect, it } from 'vitest';
import { issueMentionToken, parseIssueMentionToken } from '@core/primitives/issues/api';
import { chatMentionProvider } from './chat-mention-provider';

describe('chatMentionProvider', () => {
  it('keeps saved issue references readable without a connected tracker', () => {
    const meta = chatMentionProvider.resolve(issueMentionToken('linear', 'ENG-123'));

    expect(meta).toMatchObject({
      id: 'issue:linear:ENG-123',
      label: 'issue:linear:ENG-123',
      name: 'ENG-123',
      kind: 'issue',
    });
    expect(meta?.iconUrl).toBeUndefined();
  });

  it('delegates non-issue tokens to the workspace file provider', () => {
    const meta = chatMentionProvider.resolve('src/app.ts');

    expect(meta).toMatchObject({
      id: 'src/app.ts',
      label: 'src/app.ts',
      name: 'app.ts',
      kind: 'file',
    });
  });
});

describe('parseIssueMentionToken', () => {
  it('parses provider and identifier from issue tokens', () => {
    expect(parseIssueMentionToken('issue:github:123')).toEqual({
      token: 'issue:github:123',
      provider: 'github',
      identifier: '123',
    });
  });

  it('returns null for non-issue tokens', () => {
    expect(parseIssueMentionToken('src/app.ts')).toBeNull();
  });
});
