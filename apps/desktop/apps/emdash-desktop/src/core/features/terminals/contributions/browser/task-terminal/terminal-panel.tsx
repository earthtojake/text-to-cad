import type { TerminalShellId } from '@emdash/core/primitives/terminal-shell/api';
import { EmptyState } from '@emdash/ui/react/components';
import { Button } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useEffect, useRef, useState } from 'react';
import { useIsActiveTask } from '@core/features/tasks/api/browser/hooks/use-is-active-task';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import { useTerminalShellAvailability } from '@core/features/terminals/api/browser/use-terminal-shell-availability';
import {
  TerminalDrawerTabBar,
  type TerminalDrawerMode,
  type TerminalShellMenuState,
} from '@core/features/terminals/browser/task-terminal/terminal-drawer-tab-bar';
import { resolveTerminalPanelActiveItem } from '@core/features/terminals/browser/task-terminal/terminal-panel-selection';
import { TerminalPtyContent } from '@core/features/terminals/browser/task-terminal/terminal-pty-content';
import { usePaneScope } from '@core/features/workbench/api/browser/tabs/use-pane-scope';
import {
  useTaskComposition,
  useTerminals,
  useWorkspace,
  useWorkspaceId,
} from '@core/features/workbench/api/browser/task-composition-context';
import { lifecycleScriptsStoreToken } from '@core/features/workspaces/contributions/browser/workspace-stores';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';
import { ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';

export const TerminalsPanel = observer(function TerminalsPanel() {
  const { projectId, taskId } = useTaskViewContext();
  const workspaceId = useWorkspaceId();
  const taskView = useTaskComposition();
  const workspace = useWorkspace();
  const terminalMgr = useTerminals();
  const terminalTabView = taskView.terminalTabs;
  const lifecycleScriptsMgr = workspace.get(lifecycleScriptsStoreToken);
  const isActive = useIsActiveTask(taskId);
  const remoteConnectionId = workspace.sshConnectionId;
  const liveActionsDisabled = terminalMgr.hostAccess?.liveAction.kind === 'disabled';
  const liveActionDisabledReason = projectAvailabilityUi.getLiveActionDisabledReason(projectId);
  const [shouldLoadShellAvailability, setShouldLoadShellAvailability] = useState(false);
  const [mode, setMode] = useState<TerminalDrawerMode>(() =>
    taskView.terminalDrawerActiveItem?.kind === 'script' ? 'scripts' : 'terminals'
  );
  const previousActiveItemRef = useRef(taskView.terminalDrawerActiveItem);
  const shellAvailabilityQuery = useTerminalShellAvailability(remoteConnectionId, {
    enabled: shouldLoadShellAvailability && !liveActionsDisabled,
  });
  const shellMenuState: TerminalShellMenuState = shellAvailabilityQuery.data
    ? { kind: 'ready', availability: shellAvailabilityQuery.data }
    : shellAvailabilityQuery.isError
      ? {
          kind: 'error',
          message:
            shellAvailabilityQuery.error instanceof Error
              ? shellAvailabilityQuery.error.message
              : 'Failed to load',
        }
      : { kind: 'loading' };

  const autoFocus =
    isActive && taskView.isTerminalDrawerOpen && taskView.focusedRegion === 'bottom';

  const terminalTabs = terminalTabView.tabs;
  const lifecycleScriptTabs = lifecycleScriptsMgr?.tabs ?? [];
  const terminalIdsOpenInMain = new Set<string>();
  for (const group of taskView.paneLayout.groups) {
    for (const entry of group.pane.entries.values()) {
      if (entry.kind !== 'terminal') continue;
      const terminalId = (entry.state as { terminalId?: unknown }).terminalId;
      if (typeof terminalId === 'string') terminalIdsOpenInMain.add(terminalId);
    }
  }

  // Unified active item — spans both terminals and scripts sections.
  const activeItem = resolveTerminalPanelActiveItem({
    requestedActiveItem: taskView.terminalDrawerActiveItem,
    activeTerminalId: terminalTabView.activeTabId,
    terminalIds: terminalTabs.map((terminal) => terminal.data.id),
    scriptIds: lifecycleScriptTabs.map((script) => script.data.id),
  });

  const selectedTerminalId =
    activeItem.kind === 'terminal'
      ? activeItem.id || undefined
      : (terminalTabView.activeTabId ?? terminalTabs[0]?.data.id);
  const selectedScriptId =
    activeItem.kind === 'script'
      ? activeItem.id
      : (lifecycleScriptsMgr?.activeTabId ?? lifecycleScriptTabs[0]?.data.id);
  const activeTerminalId = mode === 'terminals' ? selectedTerminalId : undefined;
  const activeScriptId = mode === 'scripts' ? selectedScriptId : undefined;
  const activeTerminalIsOpenInMain =
    activeTerminalId !== undefined && terminalIdsOpenInMain.has(activeTerminalId);

  const activeSession =
    mode === 'terminals'
      ? activeTerminalIsOpenInMain
        ? null
        : (terminalMgr.sessions.get(activeTerminalId ?? '') ?? null)
      : (lifecycleScriptTabs.find((script) => script.data.id === activeScriptId)?.session ?? null);

  const allSessionIds = [
    ...terminalTabs
      .filter((t) => !terminalIdsOpenInMain.has(t.data.id))
      .map((t) => terminalMgr.sessions.get(t.data.id)?.sessionId)
      .filter((id): id is string => Boolean(id)),
    ...lifecycleScriptTabs.map((s) => s.session.sessionId),
  ];

  useEffect(() => {
    const previousActiveItem = previousActiveItemRef.current;
    const currentActiveItem = taskView.terminalDrawerActiveItem;
    const changed =
      currentActiveItem &&
      (currentActiveItem.kind !== previousActiveItem?.kind ||
        currentActiveItem.id !== previousActiveItem.id);

    if (changed) {
      setMode(currentActiveItem.kind === 'script' ? 'scripts' : 'terminals');
    }
    previousActiveItemRef.current = currentActiveItem;
  }, [taskView, taskView.terminalDrawerActiveItem?.id, taskView.terminalDrawerActiveItem?.kind]);

  const handleHoverTerminal = (id: string) => {
    if (liveActionsDisabled) return;
    const session = terminalMgr.sessions.get(id);
    if (session?.status === 'disconnected') void session.connect();
  };

  const activeStore = mode === 'terminals' ? terminalTabView : (lifecycleScriptsMgr ?? undefined);
  const { attachRef: attachPaneScope, instance: paneScopeInstance } = usePaneScope(
    `terminal-drawer:${projectId}:${taskId}`,
    activeStore ?? terminalTabView
  );

  const handleCreate = async (shell?: TerminalShellId) => {
    if (liveActionsDisabled) return;
    setMode('terminals');
    await taskView.openNewTerminal(shell);
  };

  const handleShellMenuOpen = () => {
    if (liveActionsDisabled) return;
    if (!shouldLoadShellAvailability) {
      setShouldLoadShellAvailability(true);
      return;
    }
    if (!shellAvailabilityQuery.isFetching) void shellAvailabilityQuery.refetch();
  };

  const handleRunScript = (id: string) => {
    const script = lifecycleScriptsMgr?.tabs.find((s) => s.data.id === id);
    if (!script || script.isRunning) return;
    setMode('scripts');
    lifecycleScriptsMgr?.setActiveTab(id);
    taskView.setTerminalDrawerActiveItem({ kind: 'script', id });
    void script.run().catch(() => {});
  };

  const handleStopScript = (id: string) => {
    const script = lifecycleScriptsMgr?.tabs.find((s) => s.data.id === id);
    if (!script) return;
    script.stop();
  };

  const handleModeChange = (nextMode: TerminalDrawerMode) => {
    setMode(nextMode);

    if (nextMode === 'terminals') {
      const terminalId = terminalTabView.activeTabId ?? terminalTabs[0]?.data.id;
      if (!terminalId) return;
      terminalTabView.setActiveTab(terminalId);
      taskView.setTerminalDrawerActiveItem({ kind: 'terminal', id: terminalId });
      return;
    }

    const scriptId = lifecycleScriptsMgr?.activeTabId ?? lifecycleScriptTabs[0]?.data.id;
    if (!scriptId) return;
    lifecycleScriptsMgr?.setActiveTab(scriptId);
    taskView.setTerminalDrawerActiveItem({ kind: 'script', id: scriptId });
  };

  const terminalEmptyState = (
    <EmptyState
      label={activeTerminalIsOpenInMain ? 'Terminal open in main pane' : 'No terminals yet'}
      description={
        activeTerminalIsOpenInMain
          ? 'Select the terminal tab in the main pane or create another terminal.'
          : "Add a terminal to run shell commands in this task's working directory."
      }
      action={
        activeTerminalIsOpenInMain ? undefined : (
          <projectAvailabilityUi.LiveActionGuard projectId={projectId}>
            <Button
              disabled={liveActionsDisabled}
              size="sm"
              variant="secondary"
              onClick={() => void handleCreate()}
              className="flex items-center gap-2"
            >
              New terminal
              <BoundShortcut command="task.newTerminal" variant="keycaps" />
            </Button>
          </projectAvailabilityUi.LiveActionGuard>
        )
      }
    />
  );

  const scriptsEmptyState = (
    <EmptyState
      label="No scripts configured"
      description="Add setup, run, or teardown scripts to your project configuration."
    />
  );

  return (
    <ViewScopeInstanceProvider instance={paneScopeInstance}>
      <div
        ref={attachPaneScope}
        tabIndex={-1}
        className="flex h-full flex-col"
        onPointerDownCapture={(event) => event.currentTarget.focus({ preventScroll: true })}
        onFocus={() => {
          taskView.setFocusedRegion('bottom');
        }}
      >
        <TerminalDrawerTabBar
          projectId={projectId}
          liveActionsDisabled={liveActionsDisabled}
          mode={mode}
          onModeChange={handleModeChange}
          lifecycleScriptsMgr={lifecycleScriptsMgr}
          activeScriptId={activeScriptId}
          onSelectScript={(id) => {
            setMode('scripts');
            lifecycleScriptsMgr?.setActiveTab(id);
            taskView.setTerminalDrawerActiveItem({ kind: 'script', id });
          }}
          onRunScript={handleRunScript}
          onStopScript={handleStopScript}
          terminalTabView={terminalTabView}
          activeTerminalId={activeTerminalId}
          shellMenuState={shellMenuState}
          onShellMenuOpen={handleShellMenuOpen}
          onRetryShellAvailability={() => void shellAvailabilityQuery.refetch()}
          onSelectTerminal={(id) => {
            setMode('terminals');
            terminalTabView.setActiveTab(id);
            taskView.setTerminalDrawerActiveItem({ kind: 'terminal', id });
          }}
          onAddTerminal={(shell) => void handleCreate(shell)}
          onRemoveTerminal={(id) => terminalTabView.removeTab(id)}
          onRenameTerminal={(id, name) => void terminalMgr.renameTerminal(id, name)}
          onHoverTerminal={handleHoverTerminal}
        />
        <TerminalPtyContent
          className="min-h-0 flex-1"
          activeSession={activeSession}
          allSessionIds={allSessionIds}
          autoFocus={autoFocus}
          emptyState={mode === 'scripts' ? scriptsEmptyState : terminalEmptyState}
          unavailableState={
            <EmptyState
              label="Terminal unavailable"
              description={liveActionDisabledReason ?? 'Live actions are unavailable.'}
            />
          }
          disabledReason={mode === 'terminals' ? liveActionDisabledReason : null}
          remoteConnectionId={remoteConnectionId}
          workspaceId={workspaceId}
          terminalPaddingBottom={0}
        />
      </div>
    </ViewScopeInstanceProvider>
  );
});
