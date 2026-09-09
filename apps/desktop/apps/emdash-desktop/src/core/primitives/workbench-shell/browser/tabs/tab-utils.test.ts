import { describe, expect, it } from 'vitest';
import { setNextTabActive, setPreviousTabActive, type TabOrderState } from './tab-utils';

describe('tab-utils', () => {
  it('wraps next tab navigation from the last tab to the first tab', () => {
    const state: TabOrderState = {
      tabOrder: ['first', 'second', 'third'],
      activeTabId: 'third',
    };

    setNextTabActive(state);

    expect(state.activeTabId).toBe('first');
  });

  it('wraps previous tab navigation from the first tab to the last tab', () => {
    const state: TabOrderState = {
      tabOrder: ['first', 'second', 'third'],
      activeTabId: 'first',
    };

    setPreviousTabActive(state);

    expect(state.activeTabId).toBe('third');
  });
});
