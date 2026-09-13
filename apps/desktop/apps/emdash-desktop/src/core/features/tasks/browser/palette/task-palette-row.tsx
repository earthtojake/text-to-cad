import { AgentStatus } from '@emdash/ui/react/components';
import { Command } from 'cmdk';
import { GitBranch, MessageSquare } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';
import { taskAgentStatus } from '@core/features/conversations/api/browser/conversation-selectors';
import { formatConversationTitleForDisplay } from '@core/features/conversations/api/browser/conversation-title-utils';
import { conversationRegistry } from '@core/features/conversations/api/browser/stores/conversation-registry';
import { getTaskStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { getTaskComposition } from '@core/features/workbench/api/browser/task-composition-selectors';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';
import type { PaletteProviderRenderProps } from '@core/primitives/palette/api';
import type { TaskPaletteMatch } from './task-palette-provider';

const PALETTE_ITEM_CLASS =
  'flex cursor-pointer items-center gap-2.5 text-foreground-muted aria-selected:text-foreground rounded-md px-2 py-2 text-sm aria-selected:bg-background-2';

export const TaskPaletteRow = observer(function TaskPaletteRow({
  match,
  value,
  onSelect,
}: PaletteProviderRenderProps<TaskPaletteMatch>) {
  const { navigate } = useNavigate();
  const { target } = match;

  const handleSelect = () => {
    if (target.kind === 'task') {
      onSelect();
      navigate(taskViewDef({ projectId: target.projectId, taskId: target.taskId }));
      return;
    }

    getTaskComposition(target.projectId, target.taskId)?.paneLayout.open(
      'conversation',
      { conversationId: target.conversationId },
      { preview: false }
    );
    onSelect();
    if (!target.keepCurrentTask) {
      navigate(taskViewDef({ projectId: target.projectId, taskId: target.taskId }));
    }
  };

  if (target.kind === 'task') {
    const taskStore = getTaskStore(target.projectId, target.taskId);
    if (taskStore) {
      return (
        <Command.Item value={value} onSelect={handleSelect} className={PALETTE_ITEM_CLASS}>
          <GitBranch size={14} className="shrink-0 text-foreground/40" />
          <span className="flex-1 truncate">{taskStore.data.name}</span>
          <AgentStatus status={taskAgentStatus(taskStore)} />
        </Command.Item>
      );
    }
  } else {
    const conversation = conversationRegistry
      .get(target.taskId)
      ?.conversations.get(target.conversationId);
    if (conversation) {
      return (
        <Command.Item value={value} onSelect={handleSelect} className={PALETTE_ITEM_CLASS}>
          <AgentIcon id={conversation.data.providerId} size={16} />
          <span className="flex-1 truncate">
            {formatConversationTitleForDisplay(
              conversation.data.providerId,
              conversation.data.title ?? ''
            )}
          </span>
          <AgentStatus status={conversation.indicatorStatus} />
        </Command.Item>
      );
    }
  }

  const Icon = target.kind === 'task' ? GitBranch : MessageSquare;
  return (
    <Command.Item value={value} onSelect={handleSelect} className={PALETTE_ITEM_CLASS}>
      <Icon size={14} className="shrink-0 text-foreground/40" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate">{match.title}</span>
        {match.subtitle && (
          <span className="truncate text-xs text-foreground/40">{match.subtitle}</span>
        )}
      </span>
    </Command.Item>
  );
});
