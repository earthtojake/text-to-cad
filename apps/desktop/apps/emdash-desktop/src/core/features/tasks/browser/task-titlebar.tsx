import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { Files, MessageSquare, PanelLeft, type LucideIcon } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import type { CadTabResource } from '@core/features/cad/api/browser/cad-tab-resource';
import { ConnectionStatusDot } from '@core/features/machines/contributions/browser/connection-status-dot';
import {
  getTaskStore,
  taskDisplayName,
  taskViewKind,
} from '@core/features/tasks/api/browser/task-state/task-selectors';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import {
  useTaskComposition,
  useWorkspace,
} from '@core/features/workbench/api/browser/task-composition-context';
import { useWorkspaceLayoutContext } from '@core/features/workbench/contributions/browser/layout-provider';
import { Titlebar } from '@core/features/workbench/contributions/browser/Titlebar';
import type { ConnectionState } from '@core/primitives/ssh/api';

export const TaskTitlebar = observer(function TaskTitlebar() {
  const { projectId, taskId } = useTaskViewContext();
  const taskStore = getTaskStore(projectId, taskId);
  const chatName = taskDisplayName(taskStore);
  const { isLeftOpen, toggleLeftSidebar } = useWorkspaceLayoutContext();

  if (taskViewKind(taskStore, projectId) !== 'ready') {
    return (
      <Titlebar
        showSidebarRecovery={false}
        leftSlot={<ChatTitle chatName={chatName} />}
        rightSlot={
          <WorkspacePanelControls
            isProjectTreeOpen={isLeftOpen}
            onProjectTreeChange={toggleLeftSidebar}
          />
        }
      />
    );
  }

  return <ReadyDesignTitlebar projectId={projectId} taskId={taskId} />;
});

const ReadyDesignTitlebar = observer(function ReadyDesignTitlebar({
  projectId,
  taskId,
}: {
  projectId: string;
  taskId: string;
}) {
  const taskStore = getTaskStore(projectId, taskId);
  const chatName = taskDisplayName(taskStore);
  const workspace = useWorkspace();
  const taskView = useTaskComposition();
  const { isLeftOpen, toggleLeftSidebar } = useWorkspaceLayoutContext();
  const activeCadModel = taskView.paneLayout.groups
    .map(({ pane }) => pane.activeResourceOfKind<CadTabResource>('cad'))
    .find((resource) => resource !== undefined);
  const isFilesOpen = !taskView.isSidebarCollapsed && taskView.sidebarTab === 'files';
  const hasWorkbenchChat = taskView.paneLayout.groups.some(({ pane }) =>
    pane.resolvedTabs.some((tab) => tab.kind === 'acp-chat' || tab.kind === 'conversation')
  );

  return (
    <Titlebar
      showSidebarRecovery={false}
      leftSlot={<ChatTitle chatName={chatName} connectionState={workspace.connectionState} />}
      rightSlot={
        <WorkspacePanelControls
          isProjectTreeOpen={isLeftOpen}
          isFilesOpen={isFilesOpen}
          isChatOpen={activeCadModel?.chatOpen ?? false}
          showFiles
          showChat={Boolean(activeCadModel) && !hasWorkbenchChat}
          onProjectTreeChange={toggleLeftSidebar}
          onFilesChange={() => taskView.chrome.commands.toggleSidebarTab('files')}
          onChatChange={(open) => activeCadModel?.setChatOpen(open)}
        />
      }
    />
  );
});

export function WorkspacePanelControls({
  isProjectTreeOpen,
  isFilesOpen = false,
  isChatOpen = false,
  showFiles = false,
  showChat = false,
  onProjectTreeChange,
  onFilesChange,
  onChatChange,
}: {
  isProjectTreeOpen: boolean;
  isFilesOpen?: boolean;
  isChatOpen?: boolean;
  showFiles?: boolean;
  showChat?: boolean;
  onProjectTreeChange: () => void;
  onFilesChange?: () => void;
  onChatChange?: (open: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Workspace layout">
      <PanelToggle
        label="threads"
        icon={PanelLeft}
        pressed={isProjectTreeOpen}
        onToggle={onProjectTreeChange}
      />
      {showChat && onChatChange ? (
        <PanelToggle
          label="chat"
          icon={MessageSquare}
          pressed={isChatOpen}
          onToggle={() => onChatChange(!isChatOpen)}
        />
      ) : null}
      {showFiles && onFilesChange ? (
        <PanelToggle label="files" icon={Files} pressed={isFilesOpen} onToggle={onFilesChange} />
      ) : null}
    </div>
  );
}

function PanelToggle({
  label,
  action,
  icon: Icon,
  pressed,
  onToggle,
}: {
  label: string;
  action?: string;
  icon: LucideIcon;
  pressed: boolean;
  onToggle: () => void;
}) {
  const actionLabel = action ?? (pressed ? `Hide ${label}` : `Show ${label}`);
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            icon
            aria-label={actionLabel}
            aria-pressed={pressed}
            onClick={onToggle}
          >
            <Icon className="size-3.5" />
          </Button>
        }
      />
      <Tooltip.Content>{actionLabel}</Tooltip.Content>
    </Tooltip.Root>
  );
}

function ChatTitle({
  chatName,
  connectionState,
}: {
  chatName?: string;
  connectionState?: ConnectionState | null;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 px-2">
      <MessageSquare className="size-4 shrink-0 text-foreground-muted" />
      <span className="max-w-64 truncate text-sm font-medium text-foreground">
        {chatName || 'Untitled chat'}
      </span>
      {connectionState ? <ConnectionStatusDot state={connectionState} /> : null}
    </div>
  );
}
