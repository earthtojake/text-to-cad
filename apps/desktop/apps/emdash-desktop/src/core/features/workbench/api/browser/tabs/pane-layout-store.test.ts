import {
  comparer,
  intercept,
  makeObservable,
  observable,
  reaction,
  runInAction,
  type IReactionDisposer,
} from 'mobx';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@core/features/browser/api/browser/client', () => ({
  getBrowserClient: async () => ({
    unregisterSession: vi.fn(),
    events: {
      subscribe: vi.fn(async () => () => {}),
    },
  }),
}));

vi.mock('@core/primitives/telemetry/browser/telemetry-scope', () => ({
  setTelemetryConversationScope: vi.fn(),
}));

vi.mock('@core/features/browser/browser/browser-tab-item', () => ({
  BrowserTabBarItem: () => null,
  BrowserTabBarItemDragPreview: () => null,
}));
vi.mock('@core/features/editor/browser/task-editor/file-tab-item', () => ({
  FileTabBarItem: () => null,
  FileTabBarItemDragPreview: () => null,
}));
vi.mock('@core/features/conversations/browser/conversation-tab-item', () => ({
  ConversationTabBarItem: () => null,
  ConversationTabBarItemDragPreview: () => null,
}));
vi.mock('@core/features/source-control/browser/diff-view/diff-tab-item', () => ({
  DiffTabBarItem: () => null,
  DiffTabBarItemDragPreview: () => null,
  diffGroupSuffix: (group: string) => `(${group})`,
}));
vi.mock('@core/features/conversations/api/browser/conversation-title-utils', () => ({
  formatConversationTitleForDisplay: (_providerId: unknown, title: unknown) =>
    (title as string) ?? 'Conversation',
}));
vi.mock('@core/features/conversations/browser/acp/acp-chat-store', () => ({
  AcpChatStore: class {
    conversationId = '';
    dispose() {}
    bootstrap() {}
  },
}));
vi.mock('@core/features/conversations/browser/acp/acp-chat-panel', () => ({
  AcpChatPanel: () => null,
}));
vi.mock('@core/primitives/logging/browser/logger', () => ({
  log: { error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() },
}));

import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import { terminalRegistry } from '@core/features/terminals/api/browser/stores/terminal-registry';
import type {
  TerminalManagerStore,
  TerminalStore,
} from '@core/features/terminals/api/browser/task-terminal/terminal-manager';
import { taskTabView } from '@core/features/workbench/api/browser/task-tab-registry';
import { PaneLayoutStore } from '@core/primitives/workbench-shell/browser/tabs/pane-layout-store';
import type {
  PaneLayoutSnapshotDocument,
  PaneLayoutSnapshotMemento,
} from '@core/primitives/workbench-shell/browser/tabs/persistence';

const testCtx = {
  viewId: 'task-1',
  projectId: 'project-1',
  workspaceId: 'workspace-1',
  taskId: 'task-1',
};

function createLayout(opts?: { onActiveTabChange?: (tabId: string | undefined) => void }) {
  return new PaneLayoutStore(taskTabView.registry, testCtx, undefined, opts);
}

const emptyDocument: PaneLayoutSnapshotDocument = {
  version: '2',
  groups: [{ groupId: 'default', tabManager: { tabs: [], activeTabId: undefined } }],
  activeGroupId: 'default',
};

/**
 * In-memory snapshot memento whose `ready` promise resolves only when the
 * test calls `finishHydration()`, simulating slow memento hydration.
 */
class FakeSnapshotMemento implements PaneLayoutSnapshotMemento {
  readonly ready: Promise<void>;
  readonly persisted: PaneLayoutSnapshotDocument[] = [];
  hasStoredValue = false;
  value: PaneLayoutSnapshotDocument = emptyDocument;
  private _resolveReady!: () => void;

  constructor() {
    this.ready = new Promise((resolve) => {
      this._resolveReady = resolve;
    });
  }

  /** Completes hydration, optionally with a stored document. */
  finishHydration(stored?: PaneLayoutSnapshotDocument): void {
    if (stored) {
      this.value = stored;
      this.hasStoredValue = true;
    }
    this._resolveReady();
  }

  read(): PaneLayoutSnapshotDocument {
    return this.value;
  }

  autoPersist(read: () => PaneLayoutSnapshotDocument): IReactionDisposer {
    return reaction(
      read,
      (value) => {
        this.value = value;
        this.hasStoredValue = true;
        this.persisted.push(value);
      },
      { equals: comparer.structural }
    );
  }
}

/** Builds a valid stored document by snapshotting a real layout with open tabs. */
function storedDocumentWithTabs(tabCount: number): PaneLayoutSnapshotDocument {
  const layout = createLayout();
  for (let i = 0; i < tabCount; i++) layout.open('browser', {});
  const document = { version: '2', ...layout.snapshot };
  layout.dispose();
  return document;
}

class FakeTerminalManagerStore {
  terminals = observable.map<string, TerminalStore>();
  sessions = observable.map();
  isLoaded: boolean;
  dispose = vi.fn();

  constructor({ terminalIds, isLoaded }: { terminalIds: string[]; isLoaded: boolean }) {
    this.isLoaded = isLoaded;
    for (const id of terminalIds) {
      this.terminals.set(id, {
        data: {
          id,
          projectId: 'project-1',
          taskId: 'task-1',
          shellId: 'system',
          name: 'Terminal 1',
        },
      } as TerminalStore);
    }
    makeObservable(this, {
      terminals: observable,
      sessions: observable,
      isLoaded: observable,
    });
  }
}

function terminalRegistryEntries(): {
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

describe('PaneLayoutStore: isViewActive and onActivate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    browserSessionStore.clear();
  });

  it('isVisible is false for all panes when isViewActive is false (default)', () => {
    const layout = createLayout();
    expect(layout.focusedPane.isVisible).toBe(false);
    layout.dispose();
  });

  it('isVisible becomes true for all panes after setViewActive(true)', () => {
    const layout = createLayout();
    runInAction(() => layout.setViewActive(true));
    expect(layout.focusedPane.isVisible).toBe(true);
    layout.dispose();
  });

  it('fires onActivate on the active tab when the view becomes active', () => {
    const layout = createLayout();
    layout.open('browser', {});
    const resource = layout.focusedPane.resolvedTabs[0]?.resource;
    const onActivate = vi.fn();
    // Inject a spy onto the resource.
    (resource as { onActivate?: () => void }).onActivate = onActivate;

    runInAction(() => layout.setViewActive(true));

    expect(onActivate).toHaveBeenCalledTimes(1);
    layout.dispose();
  });

  it('fires onActivate on the newly active tab when the active tab changes while view is active', () => {
    const layout = createLayout();
    layout.open('browser', {});
    layout.open('browser', {});

    const tabs = layout.focusedPane.resolvedTabs;
    const firstResource = tabs[0]?.resource;
    const secondResource = tabs[1]?.resource;
    const firstSpy = vi.fn();
    const secondSpy = vi.fn();
    (firstResource as { onActivate?: () => void }).onActivate = firstSpy;
    (secondResource as { onActivate?: () => void }).onActivate = secondSpy;

    runInAction(() => layout.setViewActive(true));
    // Second tab is active (opened last).
    expect(secondSpy).toHaveBeenCalledTimes(1);

    // Switch to first tab.
    runInAction(() => layout.focusedPane.setActiveTab(tabs[0]!.tabId));
    expect(firstSpy).toHaveBeenCalledTimes(1);

    layout.dispose();
  });

  it('does not fire onActivate when the view is inactive', () => {
    const layout = createLayout();
    layout.open('browser', {});
    const resource = layout.focusedPane.resolvedTabs[0]?.resource;
    const onActivate = vi.fn();
    (resource as { onActivate?: () => void }).onActivate = onActivate;

    // View stays inactive — no onActivate.
    expect(onActivate).not.toHaveBeenCalled();
    layout.dispose();
  });

  it('fires onActivate for each pane on setViewActive when split panes exist', () => {
    const layout = createLayout();
    // Open two browser tabs so splitRight() has something to split.
    layout.open('browser', {});
    layout.open('browser', {});
    layout.splitRight();

    expect(layout.groups).toHaveLength(2);

    const leftResource = layout.groups[0]!.pane.resolvedTabs.at(-1)?.resource;
    const rightResource = layout.groups[1]!.pane.resolvedTabs[0]?.resource;
    const leftSpy = vi.fn();
    const rightSpy = vi.fn();
    if (leftResource) (leftResource as { onActivate?: () => void }).onActivate = leftSpy;
    if (rightResource) (rightResource as { onActivate?: () => void }).onActivate = rightSpy;

    runInAction(() => layout.setViewActive(true));

    expect(leftSpy).toHaveBeenCalledTimes(1);
    expect(rightSpy).toHaveBeenCalledTimes(1);
    layout.dispose();
  });

  it('fires onActivate on the new resource when a preview tab is retargeted while the pane is visible', () => {
    const layout = createLayout();
    runInAction(() => layout.setViewActive(true));

    // Open the first preview tab — resource A created and activated.
    layout.open('browser', {}, { preview: true });
    const tabId = layout.focusedPane.resolvedActiveTabId;

    // Set up an intercept so the next resource written into _resources gets a
    // spy as its onActivate. This fires synchronously before the value is stored,
    // so the spy is installed before the reaction can call onActivate().
    const spy = vi.fn();
    const disposer = intercept(layout.focusedPane._resources, (change) => {
      if (change.type === 'add' || change.type === 'update') {
        (change.newValue as { onActivate?: () => void }).onActivate = spy;
      }
      return change;
    });

    // Open a second preview tab — retargets the same slot (same tabId, new resource B).
    layout.open('browser', {}, { preview: true });
    disposer();

    // Confirm this actually took the retarget path (tabId must not have changed).
    expect(layout.focusedPane.resolvedActiveTabId).toBe(tabId);

    // With the fix: the reaction detected the new resource instance at the
    // unchanged tabId and fired onActivate() on it. Without the fix the reaction
    // does not re-fire because the tracked tabId is unchanged.
    expect(spy).toHaveBeenCalledTimes(1);

    layout.dispose();
  });
});

describe('PaneLayoutStore: single-mount explicit target opens', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    browserSessionStore.clear();
    terminalRegistryEntries().set(
      'task-1',
      new FakeTerminalManagerStore({
        terminalIds: ['terminal-1'],
        isLoaded: true,
      }) as unknown as TerminalManagerStore
    );
  });

  afterEach(() => {
    terminalRegistry.release('task-1');
    terminalRegistryEntries().delete('task-1');
  });

  it('moves an existing single-mount tab to an explicit target pane', () => {
    const layout = createLayout();

    layout.open('terminal', { terminalId: 'terminal-1' });
    const sourcePaneId = layout.activePaneId;
    const sourcePane = layout.focusedPane;
    const terminalTab = sourcePane.resolvedTabs[0]!;
    const terminalResource = terminalTab.resource;

    layout.open('browser', {});
    layout.splitRight();
    const targetPaneId = layout.activePaneId;
    const targetPane = layout.focusedPane;

    expect(targetPaneId).not.toBe(sourcePaneId);
    expect(sourcePane.resolvedTabs.some((tab) => tab.kind === 'terminal')).toBe(true);
    expect(targetPane.resolvedTabs.some((tab) => tab.kind === 'terminal')).toBe(false);

    layout.open('terminal', { terminalId: 'terminal-1' }, { target: { paneId: targetPaneId } });

    expect(sourcePane.resolvedTabs.some((tab) => tab.kind === 'terminal')).toBe(false);
    const movedTerminalTab = targetPane.resolvedTabs.find((tab) => tab.kind === 'terminal');
    expect(movedTerminalTab?.tabId).toBe(terminalTab.tabId);
    expect(movedTerminalTab?.resource).toBe(terminalResource);
    expect(targetPane.resolvedActiveTabId).toBe(terminalTab.tabId);

    layout.dispose();
  });
});

describe('PaneLayoutStore: onActiveTabChange callback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    browserSessionStore.clear();
  });

  it('calls onActiveTabChange with the focused pane active tab id when a tab opens', () => {
    const onChange = vi.fn();
    const layout = createLayout({ onActiveTabChange: onChange });

    layout.open('browser', {});
    const tabId = layout.focusedPane.resolvedActiveTabId;

    expect(onChange).toHaveBeenCalledWith(tabId);
    layout.dispose();
  });

  it('calls onActiveTabChange when the focused pane active tab changes', () => {
    const onChange = vi.fn();
    const layout = createLayout({ onActiveTabChange: onChange });

    layout.open('browser', {});
    layout.open('browser', {});
    const tabs = layout.focusedPane.resolvedTabs;

    onChange.mockClear();
    runInAction(() => layout.focusedPane.setActiveTab(tabs[0]!.tabId));

    expect(onChange).toHaveBeenCalledWith(tabs[0]!.tabId);
    layout.dispose();
  });

  it('does not call onActiveTabChange after dispose', () => {
    const onChange = vi.fn();
    const layout = createLayout({ onActiveTabChange: onChange });
    layout.open('browser', {});
    onChange.mockClear();

    layout.dispose();
    // Open on the already-disposed pane shouldn't trigger (reactions are stopped).
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('PaneLayoutStore: memento-backed snapshot hydration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    browserSessionStore.clear();
  });

  it('restores a stored snapshot even when memento hydration resolves after hydrate() is called', async () => {
    // The former hasStoredValue race: a synchronous load before the memento
    // finished hydrating saw hasStoredValue === false and silently skipped
    // restore. hydrate() must instead wait for hydration and then restore.
    const stored = storedDocumentWithTabs(2);
    const memento = new FakeSnapshotMemento();
    const layout = new PaneLayoutStore(taskTabView.registry, testCtx, memento);

    const pending = layout.hydrate();
    // Hydration still in flight: nothing restored yet.
    expect(layout.focusedPane.tabOrder).toHaveLength(0);

    memento.finishHydration(stored);

    await expect(pending).resolves.toBe(true);
    expect(layout.activePaneId).toBe(stored.activeGroupId);
    expect(layout.focusedPane.tabOrder).toHaveLength(2);
    layout.dispose();
  });

  it('keeps the fresh initial pane when hydration completes with nothing stored', async () => {
    const memento = new FakeSnapshotMemento();
    const layout = new PaneLayoutStore(taskTabView.registry, testCtx, memento);
    const initialPaneId = layout.activePaneId;

    const pending = layout.hydrate();
    memento.finishHydration();

    await expect(pending).resolves.toBe(false);
    expect(layout.activePaneId).toBe(initialPaneId);
    expect(layout.focusedPane.tabOrder).toHaveLength(0);
    layout.dispose();
  });

  it('round-trips groups, tabs, active tab, and preview flags across hydrate/persist', async () => {
    // First "session": open tabs and persist through the memento.
    const memento = new FakeSnapshotMemento();
    memento.finishHydration();
    const first = new PaneLayoutStore(taskTabView.registry, testCtx, memento);
    await first.hydrate();
    first.startPersistence();

    first.open('browser', {});
    first.open('browser', {});
    runInAction(() => first.open('browser', {}, { preview: true }));

    expect(memento.persisted.length).toBeGreaterThan(0);
    const persistedDocument = memento.value;
    expect(persistedDocument.version).toBe('2');
    const firstSnapshot = first.snapshot;
    first.dispose();

    // Second "session": hydrate a fresh layout from the persisted document.
    const rehydrated = new FakeSnapshotMemento();
    const second = new PaneLayoutStore(taskTabView.registry, testCtx, rehydrated);
    const pending = second.hydrate();
    rehydrated.finishHydration(persistedDocument);
    await expect(pending).resolves.toBe(true);

    expect(second.snapshot.groups.map((g) => g.groupId)).toEqual(
      firstSnapshot.groups.map((g) => g.groupId)
    );
    expect(second.snapshot.activeGroupId).toBe(firstSnapshot.activeGroupId);
    expect(second.focusedPane.tabOrder).toHaveLength(3);
    expect(second.snapshot.groups[0]!.tabManager.activeTabId).toBe(
      firstSnapshot.groups[0]!.tabManager.activeTabId
    );
    expect(second.snapshot.groups[0]!.tabManager.tabs.map((t) => [t.tabId, t.isPreview])).toEqual(
      firstSnapshot.groups[0]!.tabManager.tabs.map((t) => [t.tabId, t.isPreview])
    );
    second.dispose();
  });
});

describe('PaneLayoutStore: pane group id restart stability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    browserSessionStore.clear();
  });

  // Spec requirement (pane-layout ownership): shared layout-storage entries
  // are keyed by pane group id, so ids must survive restarts. Ids are random
  // UUIDs at creation but must round-trip unchanged through the persisted
  // snapshot on every restore — no path may regenerate them.
  it('keeps pane group ids stable across repeated restart (hydrate/persist) cycles', async () => {
    // Session 1: split into two panes and persist.
    const memento = new FakeSnapshotMemento();
    memento.finishHydration();
    const first = new PaneLayoutStore(taskTabView.registry, testCtx, memento);
    await first.hydrate();
    first.startPersistence();
    first.open('browser', {});
    first.open('browser', {});
    first.splitRight();
    expect(first.groups).toHaveLength(2);
    const originalIds = first.groups.map((g) => g.paneId);
    const firstDocument = memento.value;
    first.dispose();

    // Session 2 (restart): hydrate from the persisted document, persist again.
    const secondMemento = new FakeSnapshotMemento();
    secondMemento.finishHydration(firstDocument);
    const second = new PaneLayoutStore(taskTabView.registry, testCtx, secondMemento);
    await expect(second.hydrate()).resolves.toBe(true);
    expect(second.groups.map((g) => g.paneId)).toEqual(originalIds);
    second.startPersistence();
    second.open('browser', {});
    const secondDocument = secondMemento.value;
    second.dispose();

    // Session 3 (second restart): ids are still the session-1 originals.
    const thirdMemento = new FakeSnapshotMemento();
    thirdMemento.finishHydration(secondDocument);
    const third = new PaneLayoutStore(taskTabView.registry, testCtx, thirdMemento);
    await expect(third.hydrate()).resolves.toBe(true);
    expect(third.groups.map((g) => g.paneId)).toEqual(originalIds);
    third.dispose();
  });
});

describe('PaneLayoutStore: onPaneDestroyed', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    browserSessionStore.clear();
  });

  it('fires with the pane id when a pane is closed directly', () => {
    const onPaneDestroyed = vi.fn();
    const layout = new PaneLayoutStore(taskTabView.registry, testCtx, undefined, {
      onPaneDestroyed,
    });
    layout.open('browser', {});
    layout.open('browser', {});
    layout.splitRight();
    const closedPaneId = layout.activePaneId;

    layout.closePane(closedPaneId);

    expect(onPaneDestroyed).toHaveBeenCalledTimes(1);
    expect(onPaneDestroyed).toHaveBeenCalledWith(closedPaneId);
    layout.dispose();
  });

  it('fires when a pane auto-closes after its last tab moves away', () => {
    const onPaneDestroyed = vi.fn();
    const layout = new PaneLayoutStore(taskTabView.registry, testCtx, undefined, {
      onPaneDestroyed,
    });
    layout.open('browser', {});
    layout.open('browser', {});
    layout.splitRight();
    const sourcePaneId = layout.activePaneId;
    const targetPaneId = layout.groups.find((g) => g.paneId !== sourcePaneId)!.paneId;
    const movedTabId = layout.focusedPane.resolvedActiveTabId!;

    layout.moveTab(movedTabId, sourcePaneId, targetPaneId);

    expect(onPaneDestroyed).toHaveBeenCalledTimes(1);
    expect(onPaneDestroyed).toHaveBeenCalledWith(sourcePaneId);
    layout.dispose();
  });

  it('does not fire for the fresh pane replaced during snapshot restore', async () => {
    const onPaneDestroyed = vi.fn();
    const stored = storedDocumentWithTabs(2);
    const memento = new FakeSnapshotMemento();
    memento.finishHydration(stored);
    const layout = new PaneLayoutStore(taskTabView.registry, testCtx, memento, {
      onPaneDestroyed,
    });

    await expect(layout.hydrate()).resolves.toBe(true);

    expect(onPaneDestroyed).not.toHaveBeenCalled();
    layout.dispose();
  });

  it('does not fire on dispose', () => {
    const onPaneDestroyed = vi.fn();
    const layout = new PaneLayoutStore(taskTabView.registry, testCtx, undefined, {
      onPaneDestroyed,
    });
    layout.open('browser', {});
    layout.open('browser', {});
    layout.splitRight();

    layout.dispose();

    expect(onPaneDestroyed).not.toHaveBeenCalled();
  });
});
