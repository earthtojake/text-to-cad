import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { JsonObject } from '@core/primitives/json/api';
import type { MementoHandle } from '@core/primitives/mementos/browser';
import type { Resolution } from '../api';
import {
  workbenchHistoryMemento,
  workbenchNavigationMemento,
  type WorkbenchHistoryState,
  type WorkbenchNavigationState,
} from '../api/mementos';
import type { NavigationHistoryStore } from './navigation-history-store';
import type { NavigationStore } from './navigation-store';
import {
  createTestNavigation,
  seedTestNavigationHost,
  testHomeViewDef as homeViewDef,
  testProjectSubject as projectSubject,
  testProjectViewDef as projectViewDef,
  testSettingsViewDef as settingsViewDef,
  testTaskViewDef as taskViewDef,
} from './testing';

const runtimeResolvers = vi.hoisted(() => new Map<string, (params: JsonObject) => Resolution>());
const dismissModal = vi.hoisted(() => vi.fn());

vi.mock('@core/primitives/views/react', () => ({
  getViewRuntime: (viewId: string) => {
    const resolve = runtimeResolvers.get(viewId);
    return resolve ? { runtime: { resolve } } : undefined;
  },
}));

vi.mock('@core/primitives/modals/react/modal-store', () => ({
  modalStore: { dismissAll: dismissModal },
}));

vi.mock('@core/primitives/telemetry/browser/focus-tracker', () => ({
  focusTracker: { transition: vi.fn(() => null) },
}));

function handle<T>(value: T, options: { hasStoredValue?: boolean } = {}): MementoHandle<T> {
  let current = value;
  return {
    get value() {
      return current;
    },
    ready: Promise.resolve(),
    isPending: false,
    hasStoredValue: options.hasStoredValue ?? true,
    read: () => current,
    update: (next) => {
      current = typeof next === 'function' ? (next as (previous: T) => T)(current) : next;
    },
    reset: async () => {},
    flush: async () => {},
    autoPersist: () => (() => {}) as ReturnType<MementoHandle<T>['autoPersist']>,
    dispose: async () => {},
  };
}

function historyHandle(
  state: WorkbenchHistoryState = workbenchHistoryMemento.default,
  hasStoredValue = true
) {
  return handle(state, { hasStoredValue });
}

function legacyHandle(
  state: WorkbenchNavigationState = workbenchNavigationMemento.default,
  hasStoredValue = true
) {
  return handle(state, { hasStoredValue });
}

let history: NavigationHistoryStore;

function buildStore(): NavigationStore {
  runtimeResolvers.clear();
  seedTestNavigationHost();
  const stores = createTestNavigation();
  history = stores.history;
  return stores.navigation;
}

describe('NavigationStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('rehydrates valid refs and strips invalid persisted entries', () => {
    const store = buildStore();
    store.attachMemento(
      historyHandle({
        version: '1',
        entries: [
          { viewId: 'ghost', params: {} },
          { viewId: 'project', params: { projectId: 'p1' } },
        ],
        index: 1,
      })
    );

    expect(store.currentRef).toMatchObject({
      viewId: 'project',
      params: { projectId: 'p1' },
    });
    expect(history.entries).toHaveLength(1);
  });

  it('seeds the new stack from the legacy navigation memento', () => {
    const store = buildStore();
    const legacy = legacyHandle({
      version: '1',
      currentViewId: 'project',
      viewParams: { project: { projectId: 'p1' } },
    });
    const reset = vi.spyOn(legacy, 'reset');
    store.attachMemento(historyHandle(workbenchHistoryMemento.default, false), legacy);

    expect(store.currentRef).toMatchObject({
      viewId: 'project',
      params: { projectId: 'p1' },
    });
    expect(history.current?.ref.viewId).toBe('project');
    expect(reset).toHaveBeenCalledOnce();
  });

  it('records resolved refs and follows redirects', () => {
    const store = buildStore();
    runtimeResolvers.set('project', () => ({ kind: 'redirect', ref: homeViewDef() }));

    store.navigate(projectViewDef({ projectId: 'gone' }));

    expect(store.currentViewId).toBe('home');
    expect(history.current?.ref.viewId).toBe('home');
  });

  it('annotates parameter refinements with the same history key', () => {
    const store = buildStore();
    store.navigate(settingsViewDef({ tab: 'general' }));
    store.navigate(settingsViewDef({ tab: 'browser' }));

    expect(history.entries).toHaveLength(1);
    expect(history.current?.ref.params).toEqual({ tab: 'browser' });
  });

  it('closes the active modal for traversals but not parameter refinements', () => {
    const store = buildStore();
    store.navigate(settingsViewDef({ tab: 'general' }));
    expect(dismissModal).toHaveBeenCalledWith('navigation');
    dismissModal.mockClear();

    store.navigate(settingsViewDef({ tab: 'browser' }));

    expect(dismissModal).not.toHaveBeenCalled();
  });

  it('uses full history refs when toggling out of settings', () => {
    const store = buildStore();
    const task = taskViewDef({ projectId: 'p1', taskId: 't1' });
    store.navigate(task);
    store.toggleSettings();
    store.toggleSettings();

    expect(store.currentRef).toEqual(task);
  });

  it('invalidates matching subject refs and resolves the current view', () => {
    const store = buildStore();
    let exists = true;
    runtimeResolvers.set('project', () =>
      exists ? { kind: 'ok' } : { kind: 'redirect', ref: homeViewDef() }
    );
    store.navigate(projectViewDef({ projectId: 'p1' }));
    exists = false;

    store.invalidateSubject(projectSubject({ projectId: 'p1' }));

    expect(store.currentViewId).toBe('home');
    expect(history.entries.every((entry) => entry.ref.viewId !== 'project')).toBe(true);
  });

  it('annotates the initial participant location and pushes later locations', () => {
    const store = buildStore();
    const ref = taskViewDef({ projectId: 'p1', taskId: 't1' });
    store.navigate(ref);

    store.reportLocation(ref, { tabId: 'tab-1' });
    expect(history.entries).toHaveLength(1);
    expect(history.current?.location).toEqual({ tabId: 'tab-1' });

    store.reportLocation(ref, { tabId: 'tab-2' });
    expect(history.entries).toHaveLength(2);
    expect(history.current?.location).toEqual({ tabId: 'tab-2' });
  });

  it('preserves the participant location when navigating to the current ref', () => {
    const store = buildStore();
    const ref = taskViewDef({ projectId: 'p1', taskId: 't1' });
    store.navigate(ref);
    store.reportLocation(ref, { tabId: 'tab-1' });

    store.navigate(ref);

    expect(history.entries).toHaveLength(1);
    expect(history.current?.location).toEqual({ tabId: 'tab-1' });
  });

  it('restores participant locations during history traversal', () => {
    const store = buildStore();
    const ref = taskViewDef({ projectId: 'p1', taskId: 't1' });
    const restoreLocation = vi.fn(() => true);
    store.navigate(ref);
    store.attachParticipant(ref, {
      captureLocation: () => undefined,
      restoreLocation,
    });
    store.reportLocation(ref, { tabId: 'tab-1' });
    store.reportLocation(ref, { tabId: 'tab-2' });

    history.back((entry) => store.applyEntry(entry));

    expect(restoreLocation).toHaveBeenCalledWith({ tabId: 'tab-1' });
  });

  it('clears a pending restoration after an explicit navigation', () => {
    const store = buildStore();
    const ref = taskViewDef({ projectId: 'p1', taskId: 't1' });
    const restoreLocation = vi.fn(() => true);
    store.applyEntry({
      ref,
      location: { tabId: 'tab-1' },
      key: `${ref.key}:tab-1`,
    });

    store.navigate(homeViewDef());
    store.navigate(ref);
    store.attachParticipant(ref, {
      captureLocation: () => undefined,
      restoreLocation,
    });

    expect(restoreLocation).not.toHaveBeenCalled();
  });

  it('emits typed traversal and refinement events', () => {
    const store = buildStore();
    const listener = vi.fn();
    store.onDidNavigate.subscribe(listener);

    store.navigate(settingsViewDef({ tab: 'general' }));
    store.navigate(settingsViewDef({ tab: 'browser' }));

    expect(listener.mock.calls.map(([event]) => event.kind)).toEqual(['traversal', 'refinement']);
  });
});
