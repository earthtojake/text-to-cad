import { describe, expect, it } from 'vitest';
import { linkedIssueDisplayIdentifier, linkedIssueMentionName } from './linked-issue';

describe('linked issue display helpers', () => {
  it('uses displayIdentifier for issue mentions when available', () => {
    expect(
      linkedIssueMentionName({
        identifier: 'internal-id',
        displayIdentifier: 'ENG-123',
        title: 'Fix issue mentions',
      })
    ).toBe('ENG-123');
  });

  it('uses title for issue mentions when the provider hides internal identifiers', () => {
    expect(
      linkedIssueMentionName({
        identifier: '37818d1b-a831-812e-8ca0-c115c72de662',
        displayIdentifier: null,
        title: 'ai health paper website',
      })
    ).toBe('ai health paper website');
  });

  it('keeps raw identifiers visible only when displayIdentifier is unspecified', () => {
    const issue = { identifier: '#42', title: 'Fix login' };

    expect(linkedIssueDisplayIdentifier(issue)).toBe('#42');
    expect(linkedIssueMentionName(issue)).toBe('#42');
  });

  it('uses a generic mention name when both display identifier and title are hidden', () => {
    expect(
      linkedIssueMentionName({
        identifier: 'internal-id',
        displayIdentifier: null,
        title: '',
      })
    ).toBe('Linked issue');
  });
});
