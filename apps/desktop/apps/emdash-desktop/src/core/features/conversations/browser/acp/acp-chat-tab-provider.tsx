import { AgentStatus } from '@emdash/ui/react/components';
import { observer } from 'mobx-react-lite';
import { formatConversationTitleForDisplay } from '@core/features/conversations/api/browser/conversation-title-utils';
import { conversationRegistry } from '@core/features/conversations/api/browser/stores/conversation-registry';
import type { TaskTabContext } from '@core/features/workbench/api/browser/tabs/task-tab-context';
import { MAX_CONVERSATION_TITLE_LENGTH } from '@core/primitives/conversations/api';
import type {
  TabEntry,
  TabHandle,
  TabProvider,
  TabViewContext,
  TabBarItemProps,
  ResolvedTab,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { createTabProvider } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider-registry';
import {
  GenericTabDragPreview,
  GenericTabItem,
} from '@core/primitives/workbench-shell/browser/tabs/tab-bar/generic-tab-item';
import { ConversationAgentIcon } from '../conversation-agent-icon';
import { AcpChatPanel } from './acp-chat-panel';
import { getAcpChatResourceManager } from './acp-chat-resource-manager';
import { AcpChatTabResource } from './acp-chat-tab-resource';

export interface AcpChatState {
  conversationId: string;
}

export interface AcpChatOpenArgs {
  conversationId: string;
}

export const AcpChatTabBarItem = observer(function AcpChatTabBarItem({
  tab,
  host,
  ctx,
}: TabBarItemProps<AcpChatTabResource>) {
  const store = tab.resource.store;
  const conversation = conversationRegistry
    .get(store.taskId)
    ?.conversations.get(store.conversationId);
  const providerId = conversation?.data.providerId ?? '';
  const rawTitle = conversation?.data.title ?? '';
  const label = conversation
    ? formatConversationTitleForDisplay(conversation.data.providerId, conversation.data.title)
    : 'ACP Chat';

  return (
    <GenericTabItem
      tab={tab}
      host={host}
      ctx={ctx}
      label={label}
      preSlot={<ConversationAgentIcon providerId={providerId} isAcp size={16} />}
      statusSlot={
        conversation ? (
          <span className="transition-opacity group-hover:opacity-0">
            <AgentStatus status={conversation.indicatorStatus} />
          </span>
        ) : undefined
      }
      kindCommands={[
        {
          id: 'conversation:rename',
          label: 'Rename',
          group: 'edit',
          shortcut: { commandId: 'workbench.tabRename' },
          run: () => host.requestRename(tab.tabId),
        },
      ]}
      renameValue={rawTitle}
      renameMaxLength={MAX_CONVERSATION_TITLE_LENGTH}
    />
  );
});

export const AcpChatTabBarItemDragPreview = observer(function AcpChatTabBarItemDragPreview({
  tab,
}: {
  tab: ResolvedTab<AcpChatTabResource>;
}) {
  const store = tab.resource.store;
  const conversation = conversationRegistry
    .get(store.taskId)
    ?.conversations.get(store.conversationId);
  const providerId = conversation?.data.providerId ?? '';
  const label = conversation
    ? formatConversationTitleForDisplay(conversation.data.providerId, conversation.data.title)
    : 'ACP Chat';

  return (
    <GenericTabDragPreview
      preSlot={<ConversationAgentIcon providerId={providerId} isAcp size={16} />}
      label={label}
    />
  );
});

const AcpChatTabContent = observer(function AcpChatTabContent() {
  return <AcpChatPanel />;
});

export const acpChatTabProvider: TabProvider<
  'acp-chat',
  AcpChatState,
  AcpChatTabResource,
  AcpChatOpenArgs
> = createTabProvider({
  kind: 'acp-chat',
  mount: 'single',
  resourceKey: (s: AcpChatState) => s.conversationId,

  onBeforeOpen: (args: AcpChatOpenArgs): AcpChatState | null => {
    return { conversationId: args.conversationId };
  },

  initialize(
    entry: TabEntry<AcpChatState>,
    _handle: TabHandle,
    ctx: TabViewContext
  ): AcpChatTabResource {
    const taskCtx = ctx as TaskTabContext;
    const manager = getAcpChatResourceManager(taskCtx.taskId, taskCtx.projectId);
    const store = manager.acquire(entry.state.conversationId);
    return new AcpChatTabResource(store);
  },

  dispose(entry: TabEntry<AcpChatState>, _resource: AcpChatTabResource, ctx: TabViewContext): void {
    const taskCtx = ctx as TaskTabContext;
    getAcpChatResourceManager(taskCtx.taskId, taskCtx.projectId).release(
      entry.state.conversationId
    );
  },

  commands: {
    rename: {
      label: 'Rename',
      exec: (resource: AcpChatTabResource, name?: string) => {
        if (name) resource.rename(name);
      },
    },
  },

  TabBarItem: AcpChatTabBarItem,
  TabBarItemDragPreview: AcpChatTabBarItemDragPreview,
  TabContent: AcpChatTabContent,
});
