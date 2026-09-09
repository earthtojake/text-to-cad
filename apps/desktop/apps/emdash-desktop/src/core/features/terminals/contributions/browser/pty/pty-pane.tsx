import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
} from 'react';
import type { FrontendPty, SessionTheme } from '@core/features/terminals/api/browser/pty/pty';
import { resolveDroppedFile } from '@core/features/terminals/api/browser/pty/terminal-image-injection';
import {
  buildTerminalImageInjection,
  clipboardDataMayContainImage,
  extractClipboardImageFiles,
  formatTerminalImagePaths,
  isNearDuplicatePaste,
} from '@core/features/terminals/api/browser/pty/terminal-image-paths';
import {
  type PasteFromClipboardHandler,
  usePty,
} from '@core/features/terminals/browser/pty/use-pty';
import {
  PaneSizingContextProvider,
  usePaneSizingContext,
} from '@core/features/terminals/contributions/browser/pty/pane-sizing-context';
import { terminalInputScope } from '@core/features/workbench/contributions/scopes';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { getDraggedWorkspaceFile } from '@core/primitives/drag-files/browser/drag-files';
import { log } from '@core/primitives/logging/browser/logger';
import { cn } from '@core/primitives/styling/browser/cn';
import { enabled, hidden, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { useViewScope } from '@core/primitives/view-scopes/react';
import {
  createPaneDimensionSink,
  PaneDimensionProvider,
} from '@core/primitives/workbench-shell/browser/tabs/pane-dimension-provider';

type Props = {
  /**
   * Deterministic PTY session ID: `makePtySessionId(projectId, scopeId, leafId)`.
   */
  sessionId: string;
  /** Pre-connected FrontendPty owned by the entity's PtySession store. */
  pty: FrontendPty;
  className?: string;
  contentFilter?: string;
  mapShiftEnterToCtrlJ?: boolean;
  readOnly?: boolean;
  /** Remote terminals are served by workspace-server runtimes and are not supported here yet. */
  remoteConnectionId?: string;
  workspaceId: string;
  themeOverride?: SessionTheme['override'];
  /** Overrides only the bottom of xterm's otherwise uniform internal padding. */
  paddingBottom?: number;
  onActivity?: () => void;
  onExit?: (info: { exitCode: number | undefined; signal?: number }) => void;
  onFirstMessage?: (message: string) => void;
  onEnterPress?: (message: string) => void;
  onInterruptPress?: () => void;
  onFind?: () => void;
};

type TerminalInputHelpers = Parameters<PasteFromClipboardHandler>[0];

async function injectTerminalImagePaths(args: {
  paths: string[];
  sessionId: string;
  remoteConnectionId: string | undefined;
  sendInput: TerminalInputHelpers['sendInput'];
  focus: TerminalInputHelpers['focus'];
}): Promise<void> {
  if (args.paths.length === 0) return;

  const platform = await (await getHostClient()).getPlatform();
  const payload = buildTerminalImageInjection(args.paths, platform);
  args.sendInput(`${payload} `, { track: false });
  args.focus();
}

// Returns true only when an image was injected, so callers can scope their
// duplicate-paste guard to the image path and leave plain-text pastes unguarded.
async function pasteClipboardImageOrText(args: {
  sessionId: string;
  remoteConnectionId: string | undefined;
  sendInput: TerminalInputHelpers['sendInput'];
  focus: TerminalInputHelpers['focus'];
  fallbackText?: string;
  preferText?: boolean;
  // Re-checked right before injecting an image; the image branch resolves
  // asynchronously, so a competing paste path may have injected in the meantime.
  shouldInjectImage?: () => boolean;
}): Promise<boolean> {
  if (args.preferText) {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        args.sendInput(text);
        return false;
      }
    } catch {
      // Clipboard text read denied or unavailable; try the image path below.
    }
  }

  try {
    const result = await (await getHostClient()).persistClipboardImage();
    if (result.success && result.path) {
      if (args.shouldInjectImage && !args.shouldInjectImage()) return false;
      await injectTerminalImagePaths({ ...args, paths: [result.path] });
      return true;
    }
  } catch (error) {
    log.warn('Terminal clipboard image paste failed', { error });
  }

  if (args.fallbackText !== undefined) {
    if (args.fallbackText) args.sendInput(args.fallbackText);
    return false;
  }

  try {
    const text = await navigator.clipboard.readText();
    if (text) args.sendInput(text);
  } catch {
    // Clipboard read denied or unavailable.
  }
  return false;
}

const PtyPaneInner = forwardRef<{ focus: () => void }, Props>(
  (
    {
      sessionId,
      pty,
      className,
      contentFilter,
      mapShiftEnterToCtrlJ,
      readOnly = false,
      remoteConnectionId,
      workspaceId,
      themeOverride,
      paddingBottom,
      onActivity,
      onFirstMessage,
      onEnterPress,
      onInterruptPress,
      onFind,
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement | null>(null);
    const { attachRef: attachTerminalScope, instance: terminalScopeInstance } = useViewScope(
      terminalInputScope({ sessionId }),
      {
        'terminal.find': () => ({
          availability: () => (onFind ? enabled : hidden),
          execute: () => onFind?.(),
        }),
      } satisfies ViewScopeImpl<typeof terminalInputScope>
    );
    const setContainerRef = useCallback(
      (element: HTMLDivElement | null) => {
        containerRef.current = element;
        attachTerminalScope(element);
      },
      [attachTerminalScope]
    );
    const lastDomImagePasteAtRef = useRef(0);
    const lastSystemPasteAtRef = useRef(0);

    const theme: SessionTheme = { override: themeOverride, paddingBottom };

    const handleSystemPaste = useCallback<PasteFromClipboardHandler>(
      ({ focus, sendInput }) => {
        if (isNearDuplicatePaste(lastDomImagePasteAtRef.current)) return;
        void (async () => {
          const injectedImage = await pasteClipboardImageOrText({
            sessionId,
            remoteConnectionId,
            focus,
            sendInput,
            preferText: true,
            shouldInjectImage: () => !isNearDuplicatePaste(lastDomImagePasteAtRef.current),
          });
          // Only guard the DOM image path against a system paste that actually
          // injected an image; plain-text pastes must not block it.
          if (injectedImage) lastSystemPasteAtRef.current = Date.now();
        })();
      },
      [remoteConnectionId, sessionId]
    );

    const { focus, sendInput } = usePty(
      {
        sessionId,
        pty,
        theme,
        mapShiftEnterToCtrlJ,
        readOnly,
        onActivity,
        onFirstMessage,
        onEnterPress,
        onInterruptPress,
        onPasteFromClipboard: readOnly ? undefined : handleSystemPaste,
      },
      containerRef
    );

    useEffect(() => {
      if (!terminalScopeInstance) return;
      terminalScopeInstance.setFocusDelegate(focus);
      return () => terminalScopeInstance.setFocusDelegate(undefined);
    }, [focus, terminalScopeInstance]);

    useImperativeHandle(ref, () => ({ focus }), [focus]);

    const injectImagePaths = useCallback(
      async (paths: string[]) => {
        await injectTerminalImagePaths({
          paths,
          sessionId,
          remoteConnectionId,
          focus,
          sendInput,
        });
      },
      [focus, remoteConnectionId, sendInput, sessionId]
    );

    const injectImageFiles = useCallback(
      async (files: File[]): Promise<boolean> => {
        const resolved = await Promise.all(files.map((file) => resolveDroppedFile(file)));
        const paths = resolved.filter((path): path is string => Boolean(path));
        if (paths.length === 0) return false;
        await injectImagePaths(paths);
        return true;
      },
      [injectImagePaths]
    );

    const handleFocus = () => {
      focus();
    };

    const handlePaste = useCallback(
      (event: React.ClipboardEvent<HTMLDivElement>) => {
        if (readOnly) return;
        const clipboardData = event.clipboardData;
        const fallbackText = clipboardData?.getData('text/plain') ?? '';
        const imageFiles = extractClipboardImageFiles(clipboardData);
        if (imageFiles.length > 0) {
          event.preventDefault();
          event.stopPropagation();
          event.nativeEvent.stopImmediatePropagation();
          if (isNearDuplicatePaste(lastSystemPasteAtRef.current)) return;
          lastDomImagePasteAtRef.current = Date.now();
          void (async () => {
            try {
              const injected = await injectImageFiles(imageFiles);
              if (injected) return;
              await pasteClipboardImageOrText({
                sessionId,
                remoteConnectionId,
                focus,
                sendInput,
                fallbackText,
              });
            } catch (error) {
              log.warn('Terminal image paste failed', { error });
            }
          })();
          return;
        }

        if (!clipboardDataMayContainImage(clipboardData)) return;

        event.preventDefault();
        event.stopPropagation();
        event.nativeEvent.stopImmediatePropagation();
        if (isNearDuplicatePaste(lastSystemPasteAtRef.current)) return;
        lastDomImagePasteAtRef.current = Date.now();
        void pasteClipboardImageOrText({
          sessionId,
          remoteConnectionId,
          focus,
          sendInput,
          fallbackText,
        });
      },
      [focus, injectImageFiles, readOnly, remoteConnectionId, sendInput, sessionId]
    );

    const handleDrop: React.DragEventHandler<HTMLDivElement> = (event) => {
      if (readOnly) return;
      try {
        event.preventDefault();
        const dt = event.dataTransfer;
        if (!dt) return;

        // In-app drag from the editor file tree. The drag payload already
        // carries the path in the workspace environment where this agent runs.
        const draggedWorkspaceFile = getDraggedWorkspaceFile(dt);
        if (draggedWorkspaceFile) {
          if (draggedWorkspaceFile.workspaceId !== workspaceId) return;

          void (async () => {
            try {
              const platform =
                draggedWorkspaceFile.targetPlatform ??
                (await (await getHostClient()).getPlatform());
              // Plain text, not bracketed paste: Claude Code swallows externally
              // injected paste markers, and the escaped single-line path needs
              // no paste protection in shells or other agent TUIs.
              sendInput(
                `${formatTerminalImagePaths(draggedWorkspaceFile.targetPaths, platform)} `,
                {
                  track: false,
                }
              );
              focus();
            } catch (error) {
              log.warn('Terminal drop failed', { error });
            }
          })();
          return;
        }

        if (!dt.files?.length) return;

        const files = Array.from(dt.files);

        void (async () => {
          try {
            const resolved = await Promise.all(files.map((file) => resolveDroppedFile(file)));
            const paths = resolved.filter((path): path is string => Boolean(path));
            if (paths.length === 0) return;
            await injectImagePaths(paths);
          } catch (error) {
            log.warn('Terminal drop failed', { error });
          }
        })();
      } catch (error) {
        log.warn('Terminal drop failed', { error });
      }
    };

    return (
      <div
        className={cn('terminal-pane flex h-full w-full min-w-0 bg', className)}
        style={{
          width: '100%',
          height: '100%',
          minHeight: 0,
          boxSizing: 'border-box',
          backgroundColor: themeOverride?.background ?? 'var(--em-surface)',
        }}
      >
        <div
          ref={setContainerRef}
          data-terminal-container
          className={cn(themeOverride?.background ? '' : 'bg-(--em-surface)')}
          style={{
            width: '100%',
            height: '100%',
            minHeight: 0,
            overflow: 'hidden',
            filter: contentFilter || undefined,
          }}
          onClick={handleFocus}
          onMouseDown={handleFocus}
          onPasteCapture={handlePaste}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
        />
      </div>
    );
  }
);

PtyPaneInner.displayName = 'TerminalPane';

/**
 * Outer wrapper: guarantees a PaneSizingContext (and therefore the per-pane
 * resize controller) is always present. When a PaneSizingContextProvider
 * ancestor already exists (e.g. conversations-panel, terminal drawer) the
 * children use that context unchanged. When none exists, PtyPane self-provisions
 * a provider scoped to its own single session ID so there is always exactly one
 * measurement path through the controller.
 */
const PtyPaneComponent = forwardRef<{ focus: () => void }, Props>((props, ref) => {
  const existing = usePaneSizingContext();
  const sink = useMemo(() => createPaneDimensionSink(), []);
  const sessionIds = useMemo(() => [props.sessionId], [props.sessionId]);

  if (existing) return <PtyPaneInner {...props} ref={ref} />;
  return (
    <PaneDimensionProvider sink={sink}>
      <PaneSizingContextProvider sessionIds={sessionIds}>
        <PtyPaneInner {...props} ref={ref} />
      </PaneSizingContextProvider>
    </PaneDimensionProvider>
  );
});
PtyPaneComponent.displayName = 'PtyPane';

export const PtyPane = React.memo(PtyPaneComponent);
