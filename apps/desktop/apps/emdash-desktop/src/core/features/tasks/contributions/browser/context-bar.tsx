import { ContextMenu } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useMemo, useState } from 'react';
import { usePromptLibrary } from '@core/features/library/api/browser/prompts/use-prompt-library';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { draftCommentsStoreToken } from '@core/features/source-control/contributions/browser/task-stores';
import {
  getRegisteredTaskData,
  getTaskStore,
} from '@core/features/tasks/api/browser/task-state/task-selectors';
import { AddContextPopover } from '@core/features/tasks/browser/context-bar/add-context-popover';
import {
  buildTaskContextActions,
  type ContextAction,
} from '@core/features/tasks/browser/context-bar/context-actions';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import { pastePromptInjection } from '@core/features/terminals/api/browser/pty/prompt-injection';
import {
  useConversations,
  useTaskComposition,
} from '@core/features/workbench/api/browser/task-composition-context';
import { usePaneContext } from '@core/primitives/workbench-shell/browser/tabs/pane-context';

interface ContextBarProps {
  conversationId: string | undefined;
  hideTrigger?: boolean;
}

export const ContextBar = observer(function ContextBar({
  conversationId,
  hideTrigger = false,
}: ContextBarProps) {
  const { projectId, taskId } = useTaskViewContext();
  const { paneId } = usePaneContext();
  const taskView = useTaskComposition();
  const conversations = useConversations();
  const { update: updateInterfaceSettings, isSaving: isSavingInterfaceSettings } =
    useAppSettingsKey('interface');
  const task = getRegisteredTaskData(projectId, taskId);
  const draftComments = getTaskStore(projectId, taskId)?.get(draftCommentsStoreToken);
  const { value: promptLibrary, isSaving: isSavingPromptLibrary } = usePromptLibrary();
  const activeSession = conversationId ? conversations.sessions.get(conversationId) : undefined;
  const activeConversationStore = conversationId
    ? conversations.conversations.get(conversationId)
    : undefined;
  const activeSessionId = activeSession?.sessionId;
  const canApplyContext = Boolean(activeSessionId);
  const hasConversation = conversations.conversations.size > 0;
  const [menuOpen, setMenuOpen] = useState(false);

  const actions = useMemo(
    () => buildTaskContextActions(task?.linkedIssue, draftComments?.comments ?? [], promptLibrary),
    [task?.linkedIssue, draftComments?.comments, promptLibrary]
  );

  const isActivePane = taskView.paneLayout.activePaneId === paneId;
  const hasVisibleContextBar = Boolean(draftComments && hasConversation && actions.length > 0);
  const popoverActions = canApplyContext ? actions : [];

  const handleApplyAction = async (
    text: string,
    action: ContextAction,
    opts?: { andSend?: boolean }
  ) => {
    if (!activeSessionId || !text) return;

    await pastePromptInjection({
      providerId: activeConversationStore?.data.providerId,
      text,
      forceBracketedPaste: true,
      sendInput: async (data) => {
        await activeSession?.connect();
        activeSession?.pty?.sendInput(data);
      },
    });

    if (action.kind === 'draft-comments') {
      draftComments?.consumeAll();
    }

    if (opts?.andSend) {
      await activeSession?.connect();
      activeSession?.pty?.sendInput('\r');
    }

    activeSession?.pty?.terminal.focus();
  };

  const hideContextBar = () => {
    updateInterfaceSettings({ hideContextBar: true });
    setMenuOpen(false);
  };

  const contextPopover = (
    <AddContextPopover
      actions={hideTrigger ? popoverActions : actions}
      disabled={!canApplyContext || isSavingPromptLibrary}
      emptyMessage={canApplyContext ? undefined : 'No active sessions'}
      hideTrigger={hideTrigger}
      hotkeyEnabled={hideTrigger ? true : undefined}
      isActivePane={isActivePane}
      onApplyAction={handleApplyAction}
      side="top"
    />
  );

  if (hideTrigger) {
    return <div className="relative h-0 w-full overflow-visible">{contextPopover}</div>;
  }

  if (!hasVisibleContextBar) return null;

  return (
    <ContextMenu.Root open={menuOpen} onOpenChange={setMenuOpen}>
      <ContextMenu.Trigger>
        <div className="flex w-full items-center justify-center px-4 pb-2">{contextPopover}</div>
      </ContextMenu.Trigger>
      <ContextMenu.Content finalFocus={false}>
        <ContextMenu.Item disabled={isSavingInterfaceSettings} onClick={hideContextBar}>
          Hide context bar
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
});
