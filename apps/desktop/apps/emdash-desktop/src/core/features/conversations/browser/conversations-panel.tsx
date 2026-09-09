import { EmptyState } from '@emdash/ui/react/components';
import { observer } from 'mobx-react-lite';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
// TODO(conversations-extraction): Pass task scope into conversations instead of importing task hooks.
import { useIsActiveTask } from '@core/features/tasks/api/browser/hooks/use-is-active-task';
// TODO(conversations-extraction): Pass task context actions into the panel as composition.
import { ContextBar } from '@core/features/tasks/contributions/browser/context-bar';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import { useTerminalSearch } from '@core/features/terminals/api/browser/pty/use-terminal-search';
import { PaneSizingContextProvider } from '@core/features/terminals/contributions/browser/pty/pane-sizing-context';
import { PtyPane } from '@core/features/terminals/contributions/browser/pty/pty-pane';
import { TerminalSearchOverlay } from '@core/features/terminals/contributions/browser/pty/terminal-search-overlay';
import {
  useConversations,
  useTaskComposition,
  useWorkspace,
  useWorkspaceId,
} from '@core/features/workbench/api/browser/task-composition-context';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { usePaneContext } from '@core/primitives/workbench-shell/browser/tabs/pane-context';
import type { ConversationTabResource } from './conversation-tab-resource';
import {
  activeConversationResource,
  activeConversationId as getActiveConversationId,
} from './pane-selectors';

export const ConversationsPanel = observer(function ConversationsPanel() {
  const { projectId, taskId } = useTaskViewContext();
  const taskView = useTaskComposition();
  const conversations = useConversations();
  const workspace = useWorkspace();
  const workspaceId = useWorkspaceId();
  const { value: interfaceSettings } = useAppSettingsKey('interface');
  const { pane } = usePaneContext();
  const isActive = useIsActiveTask(taskId);
  const remoteConnectionId = workspace.sshConnectionId;
  const disabledReason = projectAvailabilityUi.getLiveActionDisabledReason(projectId);

  const autoFocus = isActive && taskView.focusedRegion === 'main';

  // Build session ID list for PaneSizingContextProvider (all open conversation tabs).
  const allSessionIds = useMemo(() => {
    return pane.resolvedTabs
      .filter(
        (t): t is typeof t & { resource: ConversationTabResource } => t.kind === 'conversation'
      )
      .map((t) => conversations.sessions.get(t.resource.store.data.id)?.sessionId)
      .filter((id): id is string => Boolean(id));
  }, [pane.resolvedTabs, conversations.sessions]);

  const activeConversation = activeConversationResource(pane)?.store;
  const activeSession = activeConversation
    ? (conversations.sessions.get(activeConversation.data.id) ?? null)
    : null;
  const activeSessionId = activeSession?.sessionId ?? null;

  const containerRef = useRef<HTMLDivElement>(null);
  const terminalContainerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<{ focus: () => void }>(null);
  const focusPendingRef = useRef(false);

  const {
    isSearchOpen,
    searchQuery,
    searchStatus,
    searchInputRef,
    openSearch,
    closeSearch,
    handleSearchQueryChange,
    stepSearch,
  } = useTerminalSearch({
    terminal: activeSession?.pty?.terminal,
    enabled: Boolean(activeSession?.pty),
    onCloseFocus: () => terminalRef.current?.focus(),
  });

  useEffect(() => {
    if (!autoFocus) return;
    if (terminalRef.current) {
      terminalRef.current.focus();
      focusPendingRef.current = false;
    } else {
      containerRef.current?.focus();
      focusPendingRef.current = true;
    }
  }, [autoFocus, activeSessionId]);

  const sessionStatus = activeSession?.status;
  useEffect(() => {
    if (sessionStatus === 'ready' && focusPendingRef.current) {
      focusPendingRef.current = false;
      terminalRef.current?.focus();
    }
  }, [sessionStatus]);

  // State-driven notification clearing: mark the active conversation as seen
  // whenever this task view is the active route and the conversation has an
  // unseen status. This covers the split-pane case where the same tab stays
  // active — the engine's onActivate() only fires on tab identity changes.
  const activeConversationSeen = activeConversation?.seen;
  useEffect(() => {
    if (isActive && activeConversation && !activeConversation.seen) {
      activeConversation.markSeen();
    }
  }, [isActive, activeConversation, activeConversationSeen]);

  const onInterruptPress = activeConversation ? () => activeConversation.clearWorking() : undefined;
  const hideContextBarTrigger = interfaceSettings?.hideContextBar ?? false;

  // Measure the rendered height of the ContextBar so the PTY controller can
  // subtract it from the available terminal height. The ContextBar renders null
  // (height 0) when not visible and a fixed single-row bar otherwise, so the
  // measured value is always accurate without needing to know its CSS internals.
  const contextBarWrapperRef = useRef<HTMLDivElement>(null);
  const [contextBarHeight, setContextBarHeight] = useState(0);
  useEffect(() => {
    const el = contextBarWrapperRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setContextBarHeight(entry.contentRect.height);
    });
    observer.observe(el);
    // Initial measurement.
    setContextBarHeight(el.getBoundingClientRect().height);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="flex h-full flex-col bg-(--xterm-bg)">
      <div className="flex min-h-0 flex-1">
        <div
          ref={containerRef}
          tabIndex={-1}
          className="flex h-full min-w-0 flex-1 flex-col outline-none"
          onFocus={() => {
            if (isActive) taskView.setFocusedRegion('main');
          }}
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) {
              // focus left the panel — no region change needed
            }
          }}
        >
          <PaneSizingContextProvider sessionIds={allSessionIds} bottomPadding={contextBarHeight}>
            <div className="flex min-h-0 flex-1 flex-col">
              {disabledReason && activeSession?.status !== 'ready' ? (
                <EmptyState label="Conversation unavailable" description={disabledReason} />
              ) : activeSessionId && activeSession?.status === 'ready' && activeSession.pty ? (
                <div ref={terminalContainerRef} className="relative flex h-full min-h-0 flex-1">
                  <div className="flex h-full min-h-0 flex-1">
                    <TerminalSearchOverlay
                      sessionId={activeSessionId}
                      isOpen={isSearchOpen}
                      fullWidth
                      searchQuery={searchQuery}
                      searchStatus={searchStatus}
                      searchInputRef={searchInputRef}
                      onQueryChange={handleSearchQueryChange}
                      onStep={stepSearch}
                      onFind={openSearch}
                      onClose={closeSearch}
                    />
                    <PtyPane
                      ref={terminalRef}
                      sessionId={activeSessionId}
                      pty={activeSession.pty}
                      onFind={openSearch}
                      className="h-full w-full"
                      onInterruptPress={onInterruptPress}
                      mapShiftEnterToCtrlJ
                      readOnly={Boolean(disabledReason)}
                      remoteConnectionId={remoteConnectionId}
                      workspaceId={workspaceId}
                    />
                  </div>
                  {disabledReason && (
                    <div
                      className="absolute inset-x-2 top-2 z-20 rounded-md border bg-background/95 px-2 py-1 text-center text-xs text-foreground-muted shadow-sm"
                      tabIndex={0}
                      role="note"
                    >
                      {disabledReason}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </PaneSizingContextProvider>
        </div>
      </div>
      <div ref={contextBarWrapperRef} inert={disabledReason ? true : undefined}>
        <ContextBar
          conversationId={getActiveConversationId(pane)}
          hideTrigger={hideContextBarTrigger}
        />
      </div>
    </div>
  );
});
