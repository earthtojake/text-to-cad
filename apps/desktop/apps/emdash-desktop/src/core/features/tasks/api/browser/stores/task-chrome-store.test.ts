import { observable, reaction, runInAction } from 'mobx';
import { describe, expect, it } from 'vitest';
import {
  taskChromeMemento,
  type TaskChromeState,
} from '@core/features/tasks/contributions/mementos';
import { createChromeStore } from '@core/primitives/chrome-stores/browser';
import type { MementoHandle, SubjectSpace } from '@core/primitives/mementos/browser';
import { taskChromeStore, type TaskChromeStore } from './task-chrome-store';

/**
 * DOM-free harness: a hydrated fake subject space backed by an in-memory
 * observable document, so commands run through the real `createChromeStore`
 * dispatch path (state writes, ephemeral assignment) without the wire or
 * SQLite plumbing that `chrome-store.test.ts` covers for the primitive.
 */
function createStore(initial?: Partial<TaskChromeState>): TaskChromeStore {
  const document = observable.box<TaskChromeState>(
    { ...taskChromeMemento.default, ...initial },
    { deep: false }
  );
  const handle: Pick<MementoHandle<TaskChromeState>, 'value' | 'update' | 'flush'> = {
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
  } as unknown as SubjectSpace<'task'>;
  return createChromeStore(taskChromeStore, space);
}

describe('taskChromeStore sidebar commands', () => {
  it('starts from the memento default: collapsed on the conversations tab', () => {
    const store = createStore();

    expect(store.state.sidebarCollapsed).toBe(true);
    expect(store.state.sidebarTab).toBe('conversations');
    expect(store.state.terminalDrawerOpen).toBe(false);
  });

  it('toggleSidebar flips collapsed without touching the tab', () => {
    const store = createStore({ sidebarTab: 'changes' });

    store.commands.toggleSidebar();
    expect(store.state.sidebarCollapsed).toBe(false);
    expect(store.state.sidebarTab).toBe('changes');

    store.commands.toggleSidebar();
    expect(store.state.sidebarCollapsed).toBe(true);
  });

  it('collapseSidebar and expandSidebar set the flag directly', () => {
    const store = createStore({ sidebarCollapsed: false });

    store.commands.collapseSidebar();
    expect(store.state.sidebarCollapsed).toBe(true);

    store.commands.expandSidebar();
    expect(store.state.sidebarCollapsed).toBe(false);
  });

  it('openSidebarTab enforces the tab⇒expanded invariant', () => {
    const store = createStore({ sidebarCollapsed: true });

    store.commands.openSidebarTab('changes');

    expect(store.state.sidebarTab).toBe('changes');
    expect(store.state.sidebarCollapsed).toBe(false);
  });

  it('openSidebarTab expands even when the tab is already selected', () => {
    const store = createStore({ sidebarCollapsed: true, sidebarTab: 'files' });

    store.commands.openSidebarTab('files');

    expect(store.state.sidebarCollapsed).toBe(false);
  });

  it('toggleSidebarTab collapses an already-open selected tab', () => {
    const store = createStore({ sidebarCollapsed: false, sidebarTab: 'changes' });

    store.commands.toggleSidebarTab('changes');

    expect(store.state.sidebarCollapsed).toBe(true);
    expect(store.state.sidebarTab).toBe('changes');
  });

  it('toggleSidebarTab switches tabs and expands the sidebar', () => {
    const store = createStore({ sidebarCollapsed: false, sidebarTab: 'conversations' });

    store.commands.toggleSidebarTab('files');

    expect(store.state.sidebarTab).toBe('files');
    expect(store.state.sidebarCollapsed).toBe(false);
  });

  it('toggleSidebarTab opens the selected tab when the sidebar is collapsed', () => {
    const store = createStore({ sidebarCollapsed: true, sidebarTab: 'changes' });

    store.commands.toggleSidebarTab('changes');

    expect(store.state.sidebarTab).toBe('changes');
    expect(store.state.sidebarCollapsed).toBe(false);
  });

  it('sidebar commands leave focusedRegion alone', () => {
    const store = createStore();

    store.commands.openSidebarTab('files');
    store.commands.toggleSidebar();

    expect(store.ephemeral.focusedRegion).toBe('main');
  });
});

describe('taskChromeStore terminal drawer commands', () => {
  it('openTerminalDrawer opens the drawer and focuses the bottom region', () => {
    const store = createStore();

    store.commands.openTerminalDrawer();

    expect(store.state.terminalDrawerOpen).toBe(true);
    expect(store.ephemeral.focusedRegion).toBe('bottom');
  });

  it('closeTerminalDrawer closes the drawer and returns focus to main', () => {
    const store = createStore({ terminalDrawerOpen: true });
    store.commands.focusRegion('bottom');

    store.commands.closeTerminalDrawer();

    expect(store.state.terminalDrawerOpen).toBe(false);
    expect(store.ephemeral.focusedRegion).toBe('main');
  });

  it('toggleTerminalDrawer couples drawer state and focusedRegion both ways', () => {
    const store = createStore();

    store.commands.toggleTerminalDrawer();
    expect(store.state.terminalDrawerOpen).toBe(true);
    expect(store.ephemeral.focusedRegion).toBe('bottom');

    store.commands.toggleTerminalDrawer();
    expect(store.state.terminalDrawerOpen).toBe(false);
    expect(store.ephemeral.focusedRegion).toBe('main');
  });

  it('reasserts bottom focus when opening an already-open drawer', () => {
    const store = createStore({ terminalDrawerOpen: true });
    store.commands.focusRegion('main');

    store.commands.openTerminalDrawer();

    expect(store.state.terminalDrawerOpen).toBe(true);
    expect(store.ephemeral.focusedRegion).toBe('bottom');
  });
});

describe('taskChromeStore focusRegion command', () => {
  it('defaults to the main region', () => {
    const store = createStore();

    expect(store.ephemeral.focusedRegion).toBe('main');
  });

  it('sets only the ephemeral field, leaving persisted state untouched', () => {
    const store = createStore();
    const before = store.state;

    store.commands.focusRegion('bottom');

    expect(store.ephemeral.focusedRegion).toBe('bottom');
    expect(store.state).toBe(before);
  });

  it('is observable for reactions such as the focus tracker', () => {
    const store = createStore();
    const observed: Array<'main' | 'bottom'> = [];
    const dispose = reaction(
      () => store.ephemeral.focusedRegion,
      (region) => observed.push(region)
    );

    store.commands.focusRegion('bottom');
    store.commands.focusRegion('bottom');
    store.commands.focusRegion('main');

    expect(observed).toEqual(['bottom', 'main']);
    dispose();
  });
});
