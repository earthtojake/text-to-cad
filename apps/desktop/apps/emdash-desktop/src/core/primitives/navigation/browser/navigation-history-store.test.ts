import { describe, expect, it, vi } from 'vitest';
import type { JsonValue } from '@core/primitives/json/api';
import type { ViewRef } from '@core/primitives/views/api';
import type { HistoryEntry } from '../api';
import { NavigationHistoryStore } from './navigation-history-store';
import {
  testHomeViewDef as homeViewDef,
  testProjectViewDef as projectViewDef,
  testSettingsViewDef as settingsViewDef,
  testTaskViewDef as taskViewDef,
} from './testing';

function entry(ref: ViewRef, location?: JsonValue, key = ref.key): HistoryEntry {
  return { ref, ...(location === undefined ? {} : { location }), key };
}

describe('NavigationHistoryStore', () => {
  it('annotates the current entry when its navigation key is unchanged', () => {
    const history = new NavigationHistoryStore();
    const first = entry(projectViewDef({ projectId: 'project-1' }));
    const second = entry(projectViewDef({ projectId: 'project-2' }));

    history.record(first);
    history.record(second);

    expect(history.entries).toEqual([second]);
    expect(history.index).toBe(0);
  });

  it('distinguishes task refs by their history key', () => {
    const history = new NavigationHistoryStore();
    const first = entry(taskViewDef({ projectId: 'project-1', taskId: 'task-1' }));
    const second = entry(taskViewDef({ projectId: 'project-1', taskId: 'task-2' }));

    history.record(first);
    history.record(first);
    history.record(second);

    expect(history.entries).toEqual([first, second]);
  });

  it('distinguishes locations by their folded key', () => {
    const history = new NavigationHistoryStore();
    const ref = taskViewDef({ projectId: 'project-1', taskId: 'task-1' });
    const first = entry(ref, { tabId: 'tab-1' }, `${ref.key}:tab-1`);
    const second = entry(ref, { tabId: 'tab-2' }, `${ref.key}:tab-2`);

    history.record(first);
    history.record(first);
    history.record(second);

    expect(history.entries).toEqual([first, second]);
  });

  it('truncates the forward stack when a traversal is recorded', () => {
    const history = new NavigationHistoryStore();
    const home = entry(homeViewDef());
    const project = entry(projectViewDef({ projectId: 'project-1' }));
    const settings = entry(settingsViewDef());
    history.record(home);
    history.record(project);
    history.record(settings);
    history.back(() => true);

    const next = entry(taskViewDef({ projectId: 'project-1', taskId: 'task-1' }));
    history.record(next);

    expect(history.entries).toEqual([home, project, next]);
    expect(history.index).toBe(2);
    expect(history.canGoForward).toBe(false);
  });

  it('keeps the newest 50 entries and the cursor on the newest entry', () => {
    const history = new NavigationHistoryStore();

    for (let index = 0; index < 51; index++) {
      const ref = taskViewDef({ projectId: 'project-1', taskId: `task-${index}` });
      history.record(entry(ref));
    }

    expect(history.entries).toHaveLength(50);
    expect(history.entries[0]?.ref.params).toMatchObject({ taskId: 'task-1' });
    expect(history.entries.at(-1)?.ref.params).toMatchObject({ taskId: 'task-50' });
    expect(history.index).toBe(49);
  });

  it('suppresses records while applying back and forward entries', () => {
    const history = new NavigationHistoryStore();
    const home = entry(homeViewDef());
    const project = entry(projectViewDef({ projectId: 'project-1' }));
    const settings = entry(settingsViewDef());
    const apply = vi.fn(() => {
      history.record(entry(taskViewDef({ projectId: 'project-1', taskId: 'task-1' })));
      return true;
    });
    history.record(home);
    history.record(project);
    history.record(settings);

    history.back(apply);
    history.forward(apply);

    expect(apply).toHaveBeenNthCalledWith(1, project);
    expect(apply).toHaveBeenNthCalledWith(2, settings);
    expect(history.entries).toEqual([home, project, settings]);
  });

  it('splices rejected entries while traversing', () => {
    const history = new NavigationHistoryStore();
    const home = entry(homeViewDef());
    const project = entry(projectViewDef({ projectId: 'project-1' }));
    const settings = entry(settingsViewDef());
    history.record(home);
    history.record(project);
    history.record(settings);

    history.back((candidate) => candidate.key !== project.key);

    expect(history.entries).toEqual([home, settings]);
    expect(history.current).toBe(home);
  });

  it('flattens adjacent equal keys created by pruning', () => {
    const history = new NavigationHistoryStore();
    const older = entry(settingsViewDef({ tab: 'general' }));
    const newer = entry(settingsViewDef({ tab: 'browser' }));
    history.record(older);
    history.record(entry(projectViewDef({ projectId: 'project-1' })));
    history.record(newer);

    history.prune((candidate) => candidate.ref.viewId === 'project');

    expect(history.entries).toEqual([newer]);
    expect(history.current).toBe(newer);
    expect(history.index).toBe(0);
  });

  it('keeps the current survivor selected and clamps when it is pruned', () => {
    const history = new NavigationHistoryStore();
    history.record(entry(homeViewDef()));
    history.record(entry(projectViewDef({ projectId: 'project-1' })));
    history.record(entry(settingsViewDef()));
    history.back(() => true);

    history.prune((candidate) => candidate.ref.viewId === 'home');
    expect(history.current?.ref.viewId).toBe('project');

    history.prune((candidate) => candidate.ref.viewId === 'project');
    expect(history.current?.ref.viewId).toBe('settings');
  });

  it('finds the nearest matching entry before the cursor', () => {
    const history = new NavigationHistoryStore();
    const home = entry(homeViewDef());
    const project = entry(projectViewDef({ projectId: 'project-1' }));
    history.record(home);
    history.record(project);
    history.record(entry(settingsViewDef()));

    expect(history.nearestBefore((candidate) => candidate.ref.viewId !== 'settings')).toBe(project);
  });
});
