import { describe, expect, it, vi } from 'vitest';
import { TaskNavigationParticipant } from '@core/features/tasks/api/browser/stores/task-navigation-participant';

function pane(activeTabId: string | undefined, tabIds: string[]) {
  return {
    focusedPane: {
      resolvedActiveTabId: activeTabId,
      entries: new Map(tabIds.map((tabId) => [tabId, {}])),
      setActiveTab: vi.fn(),
    },
  };
}

describe('TaskNavigationParticipant', () => {
  it('captures and restores a live active tab', () => {
    const layout = pane('tab-1', ['tab-1', 'tab-2']);
    const participant = new TaskNavigationParticipant(layout);

    expect(participant.captureLocation()).toEqual({ tabId: 'tab-1' });
    expect(participant.restoreLocation({ tabId: 'tab-2' })).toBe(true);
    expect(layout.focusedPane.setActiveTab).toHaveBeenCalledWith('tab-2');
  });

  it('rejects a closed tab so traversal can splice the entry', () => {
    const layout = pane('tab-1', ['tab-1']);
    const participant = new TaskNavigationParticipant(layout);

    expect(participant.restoreLocation({ tabId: 'closed-tab' })).toBe(false);
    expect(layout.focusedPane.setActiveTab).not.toHaveBeenCalled();
  });
});
