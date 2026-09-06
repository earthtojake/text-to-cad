import { makeObservable, observable, runInAction } from 'mobx';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import type { BrowserEvent } from '@core/primitives/browser/api';

const { browserEventListeners } = vi.hoisted(() => ({
  browserEventListeners: [] as Array<(event: BrowserEvent) => void>,
}));

vi.mock('@core/features/browser/api/browser/client', () => ({
  getBrowserClient: async () => ({
    unregisterSession: vi.fn(),
    events: {
      subscribe: vi.fn(async (_key, observer: { onEvent: (event: BrowserEvent) => void }) => {
        browserEventListeners.push(observer.onEvent);
        return () => {};
      }),
    },
  }),
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getProjectManagerStore: () => ({ projects: new Map() }),
}));

vi.mock('@core/features/machines/contributions/app-stores', () => ({
  getMachinesStore: () => ({ healthFor: vi.fn(() => ({ status: 'ok' })) }),
}));

vi.mock('@core/primitives/telemetry/browser/telemetry-scope', () => ({
  setTelemetryConversationScope: vi.fn(),
}));

// Stub out the React UI components brought in by the definitions bootstrap so
// the test can run in the node Vitest project without a real DOM.
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

// ACP imports chat-ui which calls document.createElement at module load time.
// Stub out the entire chat-store chain to avoid the DOM dependency in node tests.
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

import type { BrowserTabResource } from '@core/features/browser/api/browser/browser-tab-resource';
import { terminalRegistry } from '@core/features/terminals/api/browser/stores/terminal-registry';
import type {
  TerminalManagerStore,
  TerminalStore,
} from '@core/features/terminals/api/browser/task-terminal/terminal-manager';
import { taskTabView } from '@core/features/workbench/api/browser/task-tab-registry';
import type { ResolvedTab } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { PaneStore } from '@core/primitives/workbench-shell/browser/tabs/pane-store';

const testCtx = {
  viewId: 'task-1',
  projectId: 'project-1',
  workspaceId: 'workspace-1',
  taskId: 'task-1',
};

function createTabManager() {
  return new PaneStore(taskTabView.registry, testCtx);
}

function browserResource(tab: ResolvedTab | undefined): BrowserTabResource | undefined {
  return tab?.resource as BrowserTabResource | undefined;
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

describe('PaneStore browser tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    browserSessionStore.clear();
  });

  afterEach(() => {
    terminalRegistry.release('task-1');
    terminalRegistryEntries().delete('task-1');
  });

  it('opens browser tabs backed by the default browser profile session', () => {
    const manager = createTabManager();

    manager.open('browser', { initialUrl: 'localhost:5173' });

    const tab = manager.resolvedTabs[0];
    expect(tab).toMatchObject({
      kind: 'browser',
      isActive: true,
    });
    expect(browserResource(tab)?.session?.currentUrl).toBe('http://localhost:5173/');
    expect(browserResource(tab)?.session?.partition).toBe('persist:hardcore-browser-profile');
  });

  it('snapshots and restores browser tabs through tab manager state', () => {
    const source = createTabManager();
    source.open('browser', { initialUrl: 'example.com' });

    const snapshot = source.snapshot;
    const restored = createTabManager();
    browserSessionStore.clear();
    restored.restoreSnapshot(snapshot);

    expect(restored.snapshot).toMatchObject({
      activeTabId: snapshot.activeTabId,
      tabs: [
        {
          kind: 'browser',
          session: {
            currentUrl: 'https://example.com/',
            isLoading: false,
          },
        },
      ],
    });
    expect(restored.resolvedTabs[0]?.kind).toBe('browser');
  });

  it('cleans up browser session state on close', () => {
    const manager = createTabManager();
    manager.open('browser', {});
    const tab = manager.resolvedTabs[0];
    const browserId = browserResource(tab)?.browserId ?? '';
    manager.closeTab(tab?.tabId ?? '');

    expect(browserSessionStore.getSession(browserId)).toBeUndefined();
    expect(manager.resolvedTabs).toEqual([]);
  });

  it('cleans up replaced browser sessions on snapshot restore', () => {
    const manager = createTabManager();
    manager.open('browser', {});
    const oldTab = manager.resolvedTabs[0];
    const oldBrowserId = browserResource(oldTab)?.browserId ?? '';

    manager.restoreSnapshot({ tabs: [], activeTabId: undefined });

    expect(browserSessionStore.getSession(oldBrowserId)).toBeUndefined();
    expect(manager.resolvedTabs).toEqual([]);
  });

  it('cleans up browser sessions on dispose', () => {
    const manager = createTabManager();
    manager.open('browser', {});
    const tab = manager.resolvedTabs[0];
    const browserId = browserResource(tab)?.browserId ?? '';

    manager.dispose();

    expect(browserSessionStore.getSession(browserId)).toBeUndefined();
  });

  it('detaches browser tabs for pane moves without removing session state', () => {
    const manager = createTabManager();
    manager.open('browser', {});
    const tab = manager.resolvedTabs[0];
    const browserId = browserResource(tab)?.browserId ?? '';

    const detached = manager.detachTab(tab?.tabId ?? '');

    expect(detached?.entry?.kind).toBe('browser');
    expect(browserSessionStore.getSession(browserId)).toBeDefined();
    expect(manager.resolvedTabs).toEqual([]);
  });

  it('opens webview popup requests as sibling browser tabs', async () => {
    browserEventListeners.length = 0;
    const manager = createTabManager();
    manager.open('browser', { initialUrl: 'https://source.example/' });
    const source = manager.resolvedTabs[0];
    const sourceBrowserId = browserResource(source)?.browserId ?? '';
    await vi.waitFor(() => expect(browserEventListeners).toHaveLength(1));

    browserEventListeners[0]?.({
      type: 'open-in-new-tab',
      sourceBrowserId,
      url: 'https://target.example/path',
    });

    expect(manager.resolvedTabs).toHaveLength(2);
    expect(manager.resolvedTabs[1]).toMatchObject({
      kind: 'browser',
      isActive: true,
    });
    expect(browserResource(manager.resolvedTabs[1])?.session?.currentUrl).toBe(
      'https://target.example/path'
    );
  });
});

describe('PaneStore terminal tabs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it('opens and snapshots an existing terminal as a task tab', () => {
    const manager = createTabManager();

    manager.open('terminal', { terminalId: 'terminal-1' });

    expect(manager.resolvedTabs[0]).toMatchObject({
      kind: 'terminal',
      isActive: true,
    });
    expect(manager.snapshot.tabs[0]).toMatchObject({
      kind: 'terminal',
      terminalId: 'terminal-1',
      isPreview: false,
    });
  });

  it('restores terminal tab descriptors without creating a new terminal runtime', () => {
    const restored = createTabManager();

    restored.restoreSnapshot({
      activeTabId: 'tab-terminal-1',
      tabs: [
        {
          kind: 'terminal',
          tabId: 'tab-terminal-1',
          terminalId: 'terminal-1',
          isPreview: false,
        },
      ],
    });

    expect(restored.resolvedTabs[0]).toMatchObject({
      kind: 'terminal',
      tabId: 'tab-terminal-1',
      isActive: true,
    });
    expect(terminalRegistry.get('task-1')?.terminals.has('terminal-1')).toBe(true);
  });

  it('closing a terminal task tab only closes the tab view', () => {
    const manager = createTabManager();
    manager.open('terminal', { terminalId: 'terminal-1' });

    manager.closeTab(manager.resolvedTabs[0]?.tabId ?? '');

    expect(manager.resolvedTabs).toEqual([]);
    expect(terminalRegistry.get('task-1')?.terminals.has('terminal-1')).toBe(true);
  });

  it('stale-closes terminal tabs when the drawer-owned terminal is removed', async () => {
    const manager = createTabManager();
    manager.open('terminal', { terminalId: 'terminal-1' });

    runInAction(() => {
      terminalRegistry.get('task-1')?.terminals.delete('terminal-1');
    });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(manager.resolvedTabs).toEqual([]);
  });

  it('stale-closes restored terminal tabs after initialization finishes', async () => {
    const terminals = terminalRegistry.get('task-1') as unknown as FakeTerminalManagerStore;
    runInAction(() => {
      terminals.terminals.clear();
      terminals.isLoaded = true;
    });

    const restored = createTabManager();
    restored.restoreSnapshot({
      activeTabId: 'tab-terminal-1',
      tabs: [
        {
          kind: 'terminal',
          tabId: 'tab-terminal-1',
          terminalId: 'terminal-1',
          isPreview: false,
        },
      ],
    });

    expect(restored.resolvedTabs).toHaveLength(1);

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(restored.resolvedTabs).toEqual([]);
  });
});
