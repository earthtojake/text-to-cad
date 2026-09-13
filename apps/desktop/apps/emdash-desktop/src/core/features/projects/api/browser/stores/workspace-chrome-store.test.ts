import { observable, runInAction } from 'mobx';
import { describe, expect, it } from 'vitest';
import {
  workspaceChromeMemento,
  type WorkspaceChromeState,
} from '@core/features/projects/contributions/mementos';
import { createChromeStore } from '@core/primitives/chrome-stores/browser';
import type { MementoHandle, SubjectSpace } from '@core/primitives/mementos/browser';
import { workspaceChromeStore, type WorkspaceChromeStore } from './workspace-chrome-store';

/**
 * DOM-free harness (mirrors task-chrome-store.test.ts): a hydrated fake
 * subject space backed by an in-memory observable document, so commands run
 * through the real `createChromeStore` dispatch path without wire or SQLite
 * plumbing.
 */
function createStore(initial?: Partial<WorkspaceChromeState>): WorkspaceChromeStore {
  const document = observable.box<WorkspaceChromeState>(
    { ...workspaceChromeMemento.default, ...initial },
    { deep: false }
  );
  const handle: Pick<MementoHandle<WorkspaceChromeState>, 'value' | 'update' | 'flush'> = {
    get value() {
      return document.get();
    },
    update: (next) => {
      runInAction(() => {
        document.set(typeof next === 'function' ? next(document.get()) : next);
      });
    },
    flush: () => Promise.resolve(),
  };
  const space = {
    isHydrated: true,
    handle: () => handle,
  } as unknown as SubjectSpace<'project'>;
  return createChromeStore(workspaceChromeStore, space);
}

describe('workspaceChromeStore left sidebar', () => {
  it('starts from the memento default: sidebar open, zen inactive', () => {
    const store = createStore();

    expect(store.state.leftSidebarOpen).toBe(true);
    expect(store.state.zen.active).toBe(false);
    expect(store.state.zen.restore).toEqual({});
  });

  it('toggleLeftSidebar flips the open flag', () => {
    const store = createStore();

    store.commands.toggleLeftSidebar();
    expect(store.state.leftSidebarOpen).toBe(false);

    store.commands.toggleLeftSidebar();
    expect(store.state.leftSidebarOpen).toBe(true);
  });
});

describe('workspaceChromeStore zen mode', () => {
  it('enterZenMode snapshots the overridden field and hides the sidebar', () => {
    const store = createStore({ leftSidebarOpen: true });

    store.commands.enterZenMode();

    expect(store.state.zen.active).toBe(true);
    expect(store.state.zen.restore).toEqual({ leftSidebarOpen: true });
    expect(store.state.leftSidebarOpen).toBe(false);
  });

  it('exitZenMode applies the restore snapshot and clears it', () => {
    const store = createStore({ leftSidebarOpen: true });
    store.commands.enterZenMode();

    store.commands.exitZenMode();

    expect(store.state.zen.active).toBe(false);
    expect(store.state.zen.restore).toEqual({});
    expect(store.state.leftSidebarOpen).toBe(true);
  });

  it('entering zen with the sidebar already closed restores it closed', () => {
    const store = createStore({ leftSidebarOpen: false });

    store.commands.enterZenMode();
    expect(store.state.leftSidebarOpen).toBe(false);

    store.commands.exitZenMode();
    expect(store.state.leftSidebarOpen).toBe(false);
  });

  it('enterZenMode is a no-op while zen is already active', () => {
    const store = createStore({ leftSidebarOpen: true });
    store.commands.enterZenMode();
    const before = store.state;

    store.commands.enterZenMode();

    expect(store.state).toBe(before);
  });

  it('exitZenMode is a no-op while zen is inactive', () => {
    const store = createStore({ leftSidebarOpen: false });
    const before = store.state;

    store.commands.exitZenMode();

    expect(store.state).toBe(before);
  });

  it('stale-restore: an explicit toggle while in zen wins over the snapshot', () => {
    // Enter zen with the sidebar open (restore captures open=true), then the
    // user explicitly toggles the sidebar open and closed again while in zen.
    // Exit must keep the user's last explicit value (closed) instead of
    // resurrecting the pre-zen snapshot — the inventory's stale-restore bug.
    const store = createStore({ leftSidebarOpen: true });
    store.commands.enterZenMode();

    store.commands.toggleLeftSidebar();
    expect(store.state.leftSidebarOpen).toBe(true);
    store.commands.toggleLeftSidebar();
    expect(store.state.leftSidebarOpen).toBe(false);

    store.commands.exitZenMode();
    expect(store.state.zen.active).toBe(false);
    expect(store.state.leftSidebarOpen).toBe(false);
  });

  it('a single explicit toggle while in zen also survives exit', () => {
    const store = createStore({ leftSidebarOpen: true });
    store.commands.enterZenMode();

    store.commands.toggleLeftSidebar();
    store.commands.exitZenMode();

    expect(store.state.leftSidebarOpen).toBe(true);
  });

  it('toggling while zen is inactive leaves the (empty) restore untouched', () => {
    const store = createStore();

    store.commands.toggleLeftSidebar();

    expect(store.state.zen).toEqual({ active: false, restore: {} });
  });

  it('a persisted zen document resumes with a working restore (restart-in-zen)', () => {
    // Restart is simulated by round-tripping the state through the versioned
    // schema and rebuilding the store from the parsed document.
    const before = createStore({ leftSidebarOpen: true });
    before.commands.enterZenMode();
    const serialized = workspaceChromeMemento.schema.serialize(before.state);
    const rehydrated = workspaceChromeMemento.schema.parseJson(serialized);
    expect(rehydrated).not.toBeNull();

    const store = createStore(rehydrated!);
    expect(store.state.zen.active).toBe(true);
    expect(store.state.leftSidebarOpen).toBe(false);

    store.commands.exitZenMode();
    expect(store.state.leftSidebarOpen).toBe(true);
  });
});
