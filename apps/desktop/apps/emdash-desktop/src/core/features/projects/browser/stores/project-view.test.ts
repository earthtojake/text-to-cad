import type * as React from 'react';
import { describe, expect, it } from 'vitest';
import type { ProjectViewState } from '@core/features/projects/contributions/mementos';
import type { MementoHandle } from '@core/primitives/mementos/browser';
import { ProjectViewStore } from './project-view';

const shiftClick = { shiftKey: true } as unknown as React.MouseEvent;

describe('TaskViewStore selection', () => {
  const ids = ['1', '2', '3', '4', '5'];

  function createStore() {
    const store = new ProjectViewStore(createHandle()).taskView;
    store.attachOrderedIds(() => ids);
    return store;
  }

  it('toggles membership and reports count and isSelected', () => {
    const store = createStore();

    store.toggle('2');
    store.toggle('4');
    expect(store.count).toBe(2);
    expect(store.isSelected('2')).toBe(true);

    store.toggle('2');
    expect(store.isSelected('2')).toBe(false);
    expect(store.count).toBe(1);
  });

  it('keeps the non-shift click as the range anchor across shift-clicks', () => {
    const store = createStore();

    store.toggle('1');
    store.toggle('5', shiftClick);
    store.toggle('3', shiftClick);

    expect([...store.selectedIds]).toEqual(['1', '2', '3']);
  });

  it('falls back to a plain toggle when the shift target is off-list', () => {
    const store = createStore();

    store.toggle('1');
    store.toggle('gone', shiftClick);

    expect([...store.selectedIds]).toEqual(['1', 'gone']);
  });

  it('selects an explicit range regardless of direction', () => {
    const store = createStore();

    store.selectRange('4', '2', ids);

    expect([...store.selectedIds]).toEqual(['2', '3', '4']);
  });

  it('selects all and clears', () => {
    const store = createStore();

    store.selectAll(ids);
    expect(store.count).toBe(5);

    store.clear();
    expect(store.count).toBe(0);
  });
});

describe('ProjectViewStore memento state', () => {
  it('writes project view fields through the handle', () => {
    const handle = createHandle();
    const store = new ProjectViewStore(handle);

    store.setProjectView('settings');
    store.taskView.setTab('archived');
    store.taskView.setSortBy('unread');
    store.setSelectedIssueProvider('github');

    expect(handle.value).toMatchObject({
      activeView: 'settings',
      taskViewTab: 'archived',
      taskSortBy: 'unread',
      selectedIssueProvider: 'github',
    });
  });

  it('uses last-used ordering when no persisted sort exists', () => {
    const store = new ProjectViewStore(createHandle());

    expect(store.taskView.sortBy).toBe('updated-at');
  });
});

function createHandle(): MementoHandle<ProjectViewState> {
  let value: ProjectViewState = {
    version: '1',
    activeView: 'tasks',
    taskViewTab: 'active',
  };
  return {
    get value() {
      return value;
    },
    ready: Promise.resolve(),
    isPending: false,
    hasStoredValue: true,
    read: () => value,
    update: (next) => {
      value = typeof next === 'function' ? next(value) : next;
    },
    reset: async () => {},
    flush: async () => {},
    autoPersist: () => (() => {}) as ReturnType<MementoHandle<ProjectViewState>['autoPersist']>,
    dispose: async () => {},
  };
}
