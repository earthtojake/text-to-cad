import { describe, expect, it } from 'vitest';
import { shouldShowTaskPaneTabBar } from './task-pane-chrome';

describe('shouldShowTaskPaneTabBar', () => {
  it('does not label the task chat a second time', () => {
    expect(shouldShowTaskPaneTabBar(['acp-chat'])).toBe(false);
  });

  it('keeps tabs when there is something to identify or switch between', () => {
    expect(shouldShowTaskPaneTabBar(['conversation', 'acp-chat'])).toBe(true);
    expect(shouldShowTaskPaneTabBar(['cad'])).toBe(true);
    expect(shouldShowTaskPaneTabBar(['file'])).toBe(true);
  });

  it('shows true artifact tabs when there is something to switch between', () => {
    expect(shouldShowTaskPaneTabBar(['cad', 'file'])).toBe(true);
    expect(shouldShowTaskPaneTabBar(['file', 'file'])).toBe(true);
  });

  it('keeps generic chrome for mixed and extension panes', () => {
    expect(shouldShowTaskPaneTabBar(['acp-chat', 'cad'])).toBe(true);
    expect(shouldShowTaskPaneTabBar(['browser'])).toBe(true);
    expect(shouldShowTaskPaneTabBar(['terminal'])).toBe(true);
  });
});
