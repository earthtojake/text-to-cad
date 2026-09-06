import { observer } from 'mobx-react-lite';
import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import { TERMINAL_PADDING_PX } from '@core/features/terminals/api/browser/pty/pty';
import { type PtySession } from '@core/features/terminals/api/browser/pty/pty-session';
import { useTerminalSearch } from '@core/features/terminals/api/browser/pty/use-terminal-search';
import { PaneSizingContextProvider } from '@core/features/terminals/contributions/browser/pty/pane-sizing-context';
import { PtyPane } from '@core/features/terminals/contributions/browser/pty/pty-pane';
import { TerminalSearchOverlay } from '@core/features/terminals/contributions/browser/pty/terminal-search-overlay';
import { cn } from '@core/primitives/styling/browser/cn';
import { cssVar } from '@core/primitives/styling/browser/cssVars';
import {
  createPaneDimensionSink,
  PaneDimensionProvider,
} from '@core/primitives/workbench-shell/browser/tabs/pane-dimension-provider';

export interface TerminalPtyContentProps {
  activeSession: PtySession | null;
  allSessionIds: string[];
  autoFocus?: boolean;
  onFocusChange?: (focused: boolean) => void;
  onEnterPress?: () => void;
  onInterruptPress?: () => void;
  mapShiftEnterToCtrlJ?: boolean;
  emptyState: ReactNode;
  unavailableState?: ReactNode;
  remoteConnectionId?: string;
  workspaceId: string;
  /** Defaults to the standard uniform xterm inset. */
  terminalPaddingBottom?: number;
  disabledReason?: string | null;
  className?: string;
}

export const TerminalPtyContent = observer(function TerminalPtyContent({
  activeSession,
  allSessionIds,
  autoFocus,
  onFocusChange,
  onEnterPress,
  onInterruptPress,
  mapShiftEnterToCtrlJ,
  emptyState,
  unavailableState,
  remoteConnectionId,
  workspaceId,
  terminalPaddingBottom = TERMINAL_PADDING_PX,
  disabledReason,
  className,
}: TerminalPtyContentProps) {
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

  // Fire when autoFocus becomes true or the active session changes.
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

  // Fire when the session transitions to 'ready'.
  const sessionStatus = activeSession?.status;
  useEffect(() => {
    if (sessionStatus === 'ready' && focusPendingRef.current) {
      focusPendingRef.current = false;
      terminalRef.current?.focus();
    }
  }, [sessionStatus]);

  const sessionIds = useMemo(() => allSessionIds, [allSessionIds]);
  const dimensionSink = useMemo(() => createPaneDimensionSink(), []);
  // The resize controller already accounts for uniform padding; pass only the
  // delta so its row count stays aligned with the drawer-specific CSS inset.
  const gridBottomPadding = terminalPaddingBottom - TERMINAL_PADDING_PX;

  const hasSessions = sessionIds.length > 0;

  // This panel can mount while its resizable panel still has a transient
  // zero-height layout — the panel group assigns real sizes only after the
  // entry commit (observed as height 0 on drawer open). Mounting xterm against
  // that geometry forces a synchronous measure/re-layout cascade inside the
  // commit, which is the drawer-open frame spike. Defer the terminal subtree
  // until the pane reports a real height: the sink is observable, so the first
  // non-zero measurement re-renders this observer and the terminal mounts
  // once, with correct pre-mount dimensions already computed by the pane's
  // resize controller.
  const paneMeasured = (dimensionSink.dimensions?.height ?? 0) > 0;

  return (
    <div
      ref={containerRef}
      tabIndex={-1}
      className={cn('flex h-full flex-col outline-none', className)}
      onFocus={() => onFocusChange?.(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          onFocusChange?.(false);
        }
      }}
    >
      <PaneDimensionProvider sink={dimensionSink}>
        <PaneSizingContextProvider sessionIds={sessionIds} bottomPadding={gridBottomPadding}>
          {disabledReason && activeSession?.status !== 'ready' ? (
            (unavailableState ?? emptyState)
          ) : !hasSessions || !activeSession ? (
            emptyState
          ) : (
            <div className="flex min-h-0 flex-1 flex-col">
              {paneMeasured &&
              activeSessionId &&
              activeSession?.status === 'ready' &&
              activeSession.pty ? (
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
                      themeOverride={{
                        background: cssVar('--em-surface-paper'),
                      }}
                      paddingBottom={terminalPaddingBottom}
                      onEnterPress={onEnterPress}
                      onInterruptPress={onInterruptPress}
                      mapShiftEnterToCtrlJ={mapShiftEnterToCtrlJ}
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
          )}
        </PaneSizingContextProvider>
      </PaneDimensionProvider>
    </div>
  );
});
