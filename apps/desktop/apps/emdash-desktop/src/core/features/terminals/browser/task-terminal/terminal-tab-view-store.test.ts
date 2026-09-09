import { observable, runInAction } from 'mobx';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { TaskTerminalSelectionState } from '@core/features/tasks/contributions/mementos';
import { terminalRegistry } from '@core/features/terminals/api/browser/stores/terminal-registry';
import type {
  TerminalManagerStore,
  TerminalStore,
} from '@core/features/terminals/api/browser/task-terminal/terminal-manager';
import { TerminalTabViewStore } from '@core/features/terminals/api/browser/task-terminal/terminal-tab-view-store';
import type { MementoHandle } from '@core/primitives/mementos/browser';
import type { Terminal } from '@core/primitives/terminals/api';

vi.mock('./terminal-manager', () => ({
  TerminalManagerStore: class {},
}));

function makeTerminal(id: string, name = 'Terminal 1'): TerminalStore {
  return {
    data: {
      id,
      projectId: 'project-1',
      taskId: 'task-1',
      shellId: 'system',
      name,
    } satisfies Terminal,
  } as TerminalStore;
}

function makeManager(terminals: TerminalManagerStore['terminals']): TerminalManagerStore {
  return { terminals, isLoaded: true, dispose: vi.fn() } as unknown as TerminalManagerStore;
}

function makeLoadingManager(terminals: TerminalManagerStore['terminals']): TerminalManagerStore & {
  isLoaded: boolean;
} {
  return observable({
    terminals,
    isLoaded: false,
    dispose: vi.fn(),
  }) as unknown as TerminalManagerStore & { isLoaded: boolean };
}

function makeHandle(
  initial: Partial<TaskTerminalSelectionState> = {}
): MementoHandle<TaskTerminalSelectionState> {
  let value: TaskTerminalSelectionState = {
    version: '1',
    tabOrder: [],
    ...initial,
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
    autoPersist: () =>
      (() => {}) as ReturnType<MementoHandle<TaskTerminalSelectionState>['autoPersist']>,
    dispose: async () => {},
  };
}

function registryEntries(): {
  set(taskId: string, manager: TerminalManagerStore): void;
  delete(taskId: string): boolean;
} {
  return (
    terminalRegistry as unknown as {
      entries: {
        set(taskId: string, manager: TerminalManagerStore): void;
        delete(taskId: string): boolean;
      };
    }
  ).entries;
}

describe('TerminalTabViewStore', () => {
  afterEach(() => {
    terminalRegistry.release('task-1');
    registryEntries().delete('task-1');
  });

  it('syncs terminal ids when the terminal manager becomes available after construction', () => {
    const terminals = observable.map<string, TerminalStore>();
    const view = new TerminalTabViewStore(
      makeHandle(),
      () => terminalRegistry.get('task-1') ?? null
    );

    runInAction(() => {
      registryEntries().set('task-1', makeManager(terminals));
      terminals.set('terminal-2', makeTerminal('terminal-2', 'Terminal 2'));
    });

    expect(view.tabOrder).toEqual(['terminal-2']);

    view.dispose();
  });

  it('reconciles restored snapshots with already-loaded terminal records', () => {
    const terminals = observable.map<string, TerminalStore>();
    terminals.set('terminal-1', makeTerminal('terminal-1', 'Terminal 1'));
    terminals.set('terminal-2', makeTerminal('terminal-2', 'Terminal 2'));
    registryEntries().set('task-1', makeManager(terminals));

    const view = new TerminalTabViewStore(
      makeHandle({
        tabOrder: ['terminal-2'],
        activeTabId: 'terminal-2',
      }),
      () => terminalRegistry.get('task-1') ?? null
    );

    expect(view.tabOrder).toEqual(['terminal-2', 'terminal-1']);
    expect(view.activeTabId).toBe('terminal-2');

    view.dispose();
  });

  it('falls back to the first live terminal when the restored active terminal is stale', () => {
    const terminals = observable.map<string, TerminalStore>();
    terminals.set('terminal-1', makeTerminal('terminal-1', 'Terminal 1'));
    terminals.set('terminal-2', makeTerminal('terminal-2', 'Terminal 2'));
    registryEntries().set('task-1', makeManager(terminals));

    const view = new TerminalTabViewStore(
      makeHandle({
        tabOrder: ['deleted-terminal'],
        activeTabId: 'deleted-terminal',
      }),
      () => terminalRegistry.get('task-1') ?? null
    );

    expect(view.tabOrder).toEqual(['terminal-1', 'terminal-2']);
    expect(view.activeTabId).toBe('terminal-1');

    view.dispose();
  });

  it('reconciles a restored snapshot after the terminal manager loads later', () => {
    const view = new TerminalTabViewStore(
      makeHandle({
        tabOrder: ['deleted-terminal'],
        activeTabId: 'deleted-terminal',
      }),
      () => terminalRegistry.get('task-1') ?? null
    );

    const terminals = observable.map<string, TerminalStore>();
    terminals.set('terminal-1', makeTerminal('terminal-1', 'Terminal 1'));

    runInAction(() => {
      registryEntries().set('task-1', makeManager(terminals));
    });

    expect(view.tabOrder).toEqual(['terminal-1']);
    expect(view.activeTabId).toBe('terminal-1');

    view.dispose();
  });

  it('clears stale restored ids when an empty terminal list finishes loading', () => {
    const terminals = observable.map<string, TerminalStore>();
    const manager = makeLoadingManager(terminals);
    registryEntries().set('task-1', manager);

    const view = new TerminalTabViewStore(
      makeHandle({
        tabOrder: ['deleted-terminal'],
        activeTabId: 'deleted-terminal',
      }),
      () => terminalRegistry.get('task-1') ?? null
    );

    runInAction(() => {
      manager.isLoaded = true;
    });

    expect(view.tabOrder).toEqual([]);
    expect(view.activeTabId).toBeUndefined();

    view.dispose();
  });
});
