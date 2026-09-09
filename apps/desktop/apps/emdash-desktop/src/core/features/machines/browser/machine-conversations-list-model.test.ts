import { observable, runInAction } from 'mobx';
import { describe, expect, it } from 'vitest';
import type { HostConversationRow } from '@core/primitives/conversations/api';
import type { MachineConversationItem } from './machine-conversation-rows';
import { createMachineConversationsListView } from './machine-conversations-list-model';

describe('createMachineConversationsListView', () => {
  it('re-derives from the reactive getter when items change', () => {
    const box = observable.box<MachineConversationItem[]>([], { deep: false });
    const view = createMachineConversationsListView({ kind: 'sync', items: () => box.get() });

    expect(view.store.visibleItems).toEqual([]);

    runInAction(() => box.set([item({ id: 'a' }), item({ id: 'b' })]));
    expect(view.store.orderedIds).toEqual(['a', 'b']);
  });

  it('searches title, provider, workspace path, and link names', () => {
    const box = observable.box<MachineConversationItem[]>(
      [
        item({ id: 'a', title: 'Fix login bug' }),
        item({ id: 'b', provider: 'claude' }),
        item({ id: 'c', workspacePath: '/repos/emdash' }),
        item({ id: 'd', taskName: 'Migrate lists' }),
        item({ id: 'e', projectName: 'Docs Site' }),
      ],
      { deep: false }
    );
    const view = createMachineConversationsListView({ kind: 'sync', items: () => box.get() });
    const search = (query: string) => {
      view.store.search!.setQuery(query);
      return view.store.orderedIds;
    };

    expect(search('login')).toEqual(['a']);
    expect(search('CLAUDE')).toEqual(['b']);
    expect(search('/repos/emdash')).toEqual(['c']);
    expect(search('migrate')).toEqual(['d']);
    expect(search('docs site')).toEqual(['e']);
    expect(search('nothing-matches')).toEqual([]);
    expect(search('')).toEqual(['a', 'b', 'c', 'd', 'e']);
  });
});

function item(overrides: Partial<HostConversationRow>): MachineConversationItem {
  return {
    conversation: {
      id: 'conversation-1',
      title: 'Untitled',
      provider: null,
      type: null,
      projectId: null,
      taskId: null,
      projectName: null,
      taskName: null,
      workspacePath: null,
      lastSessionActivityAt: null,
      observedStatus: 'present',
      lastObservedAt: null,
      createdAt: '2026-08-01T00:00:00.000Z',
      updatedAt: '2026-08-01T00:00:00.000Z',
      pendingRemoval: false,
      ...overrides,
    },
    linked: false,
    missing: false,
    dangling: false,
    pendingRemoval: false,
  };
}
