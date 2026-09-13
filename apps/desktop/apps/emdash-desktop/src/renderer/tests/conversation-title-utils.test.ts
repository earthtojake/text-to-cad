import { describe, expect, it } from 'vitest';
import {
  formatConversationTitleForDisplay,
  nextDefaultConversationTitle,
} from '@core/features/conversations/api/browser/conversation-title-utils';

describe('nextDefaultConversationTitle', () => {
  it('fills the smallest missing index for a provider', () => {
    const title = nextDefaultConversationTitle('codex', [
      { providerId: 'codex', title: 'codex (1)' },
      { providerId: 'codex', title: 'codex (3)' },
    ]);

    expect(title).toBe('Codex (2)');
  });

  it('appends when there are no gaps', () => {
    const title = nextDefaultConversationTitle('codex', [
      { providerId: 'codex', title: 'codex (1)' },
      { providerId: 'codex', title: 'codex (2)' },
      { providerId: 'codex', title: 'codex (3)' },
    ]);

    expect(title).toBe('Codex (4)');
  });

  it('ignores other providers and non-default titles', () => {
    const title = nextDefaultConversationTitle('codex', [
      { providerId: 'claude', title: 'claude (1)' },
      { providerId: 'codex', title: 'release-triage' },
      { providerId: 'codex', title: 'codex (2)' },
    ]);

    expect(title).toBe('Codex (1)');
  });

  it('formats existing lowercase default titles for display', () => {
    expect(formatConversationTitleForDisplay('codex', 'codex (2)')).toBe('Codex (2)');
    expect(formatConversationTitleForDisplay('gemini', 'gemini (1)')).toBe('Gemini (1)');
  });

  it('leaves custom conversation titles unchanged', () => {
    expect(formatConversationTitleForDisplay('codex', 'release-triage')).toBe('release-triage');
  });
});
