import { observer } from 'mobx-react-lite';
import type { TaskTabContext } from '@core/features/workbench/api/browser/tabs/task-tab-context';
import type {
  TabEntry,
  TabHandle,
  TabProvider,
  TabViewContext,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { createTabProvider } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider-registry';
import { ConversationTabBarItem, ConversationTabBarItemDragPreview } from './conversation-tab-item';
import { ConversationTabResource } from './conversation-tab-resource';
import { ConversationsPanel } from './conversations-panel';
import { getConversationSessionManager } from './stores/conversation-session-manager';

export interface ConversationState {
  conversationId: string;
}

export interface ConversationOpenArgs {
  conversationId: string;
}

/**
 * Mounts ConversationsPanel unconditionally. Visibility is managed by PaneContent
 * via visibility:hidden + inert so PTY sessions survive tab switches.
 */
const ConversationTabContent = observer(function ConversationTabContent() {
  return <ConversationsPanel />;
});

export const conversationTabProvider: TabProvider<
  'conversation',
  ConversationState,
  ConversationTabResource,
  ConversationOpenArgs
> = createTabProvider({
  kind: 'conversation',
  mount: 'single',
  resourceKey: (s: ConversationState) => s.conversationId,

  onBeforeOpen: (args: ConversationOpenArgs): ConversationState | null => {
    return { conversationId: args.conversationId };
  },

  initialize(
    entry: TabEntry<ConversationState>,
    handle: TabHandle,
    ctx: TabViewContext
  ): ConversationTabResource {
    const taskCtx = ctx as TaskTabContext;
    const sessionManager = getConversationSessionManager(taskCtx.taskId);
    const store = sessionManager.acquire(entry.state.conversationId);
    if (!store) {
      // Conversation not found; return a dummy resource that will auto-close.
      const dummy: ConversationTabResource = {
        store: undefined as never,
        dispose: () => {
          sessionManager.release(entry.state.conversationId);
        },
        onActivate: undefined,
      } as unknown as ConversationTabResource;
      // Auto-close on next tick.
      setTimeout(() => void handle.close(), 0);
      return dummy;
    }
    return new ConversationTabResource(store, taskCtx.taskId, handle);
  },

  dispose(
    entry: TabEntry<ConversationState>,
    _resource: ConversationTabResource,
    ctx: TabViewContext
  ): void {
    const taskCtx = ctx as TaskTabContext;
    getConversationSessionManager(taskCtx.taskId).release(entry.state.conversationId);
  },

  commands: {
    rename: {
      label: 'Rename',
      exec: (resource: ConversationTabResource, name?: string) => {
        if (name) resource.rename(name);
      },
    },
  },

  TabBarItem: ConversationTabBarItem,
  TabBarItemDragPreview: ConversationTabBarItemDragPreview,
  TabContent: ConversationTabContent,
});
