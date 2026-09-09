import { describe, expect, it } from 'vitest';
import { getBranchTooltipText, getPublishTooltipText } from './git-status-tooltips';

describe('git status tooltips', () => {
  it('shows full branch name for branch tooltip', () => {
    expect(getBranchTooltipText('main', 'branch')).toBe('main');
  });

  it('shows detached HEAD message with short hash', () => {
    expect(getBranchTooltipText('abc1234', 'detached')).toBe('Detached HEAD at abc1234');
  });

  it('shows initial-commit guidance for unborn branch tooltip', () => {
    expect(getBranchTooltipText('main', 'unborn')).toBe('Create an initial commit first');
  });

  it('shows cannot-publish message when HEAD is detached', () => {
    expect(
      getPublishTooltipText({
        isPublishing: false,
        headDisplay: 'abc1234',
        headKind: 'detached',
        shouldOfferAddRemote: false,
      })
    ).toBe('Cannot publish: HEAD is detached');
  });

  it('shows initial-commit guidance for disabled publish button when branch is unborn', () => {
    expect(
      getPublishTooltipText({
        isPublishing: false,
        headDisplay: 'main',
        headKind: 'unborn',
        shouldOfferAddRemote: true,
      })
    ).toBe('Create an initial commit first');
  });

  it('preserves existing publish tooltip behavior when branch exists', () => {
    expect(
      getPublishTooltipText({
        isPublishing: false,
        headDisplay: 'main',
        headKind: 'branch',
        shouldOfferAddRemote: true,
      })
    ).toBe('Create or link a remote, then publish this branch');

    expect(
      getPublishTooltipText({
        isPublishing: false,
        headDisplay: 'main',
        headKind: 'branch',
        shouldOfferAddRemote: false,
      })
    ).toBe('Publish branch');
  });
});
