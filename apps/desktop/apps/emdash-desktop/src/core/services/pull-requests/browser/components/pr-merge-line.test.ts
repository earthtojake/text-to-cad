import { describe, expect, it } from 'vitest';
import { getPrMergeLineActionText } from './pr-merge-line';

describe('getPrMergeLineActionText', () => {
  it('uses open PR wording while the PR can still be merged', () => {
    expect(getPrMergeLineActionText('open')).toBe('wants to merge');
  });

  it('uses merged wording after the PR is merged', () => {
    expect(getPrMergeLineActionText('merged')).toBe('merged');
  });

  it('distinguishes closed unmerged PRs from merged PRs', () => {
    expect(getPrMergeLineActionText('closed')).toBe('was closed without merging');
  });
});
