import { type Terminal } from '@xterm/xterm';
import { reaction } from 'mobx';
import { useCallback, useEffect, useRef } from 'react';
import type { FrontendPty, SessionTheme } from '@core/features/terminals/api/browser/pty/pty';
import { TERMINAL_PADDING_PX } from '@core/features/terminals/api/browser/pty/pty';
import { measureDimensions } from '@core/features/terminals/api/browser/pty/pty-dimensions';
import { buildTerminalFontFamily } from '@core/features/terminals/api/browser/pty/terminal-font';
import { getCellMetrics } from '@core/features/terminals/api/browser/pty/xterm-cell-metrics';
import { usePaneSizingContext } from '@core/features/terminals/contributions/browser/pty/pane-sizing-context';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { log } from '@core/primitives/logging/browser/logger';
import { TERMINAL_FONT_SIZE_DEFAULT } from '@core/primitives/terminals/api';
import type { AppSettings } from '@core/services/settings/api';
import { getAppSettingsClient } from '@core/services/settings/api/client';
import { isRealTaskInput, SubmittedInputBuffer } from './pty-input-buffer';
import {
  CTRL_J_ASCII,
  CTRL_U_ASCII,
  shouldCopySelectionFromTerminal,
  shouldHandleInterruptFromTerminal,
  shouldKillLineFromTerminal,
  shouldMapShiftEnterToCtrlJ,
  shouldPasteToTerminal,
} from './pty-keybindings';
import { getTerminalContextLink } from './terminal-context-link';

const IS_MAC_PLATFORM =
  typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);
const IS_WINDOWS_PLATFORM = typeof navigator !== 'undefined' && /Win/.test(navigator.platform);
const LAST_SELECTION_COPY_GRACE_MS = 2_000;

function getRecentSelection(selection: { text: string; capturedAt: number } | null): string {
  if (!selection) return '';
  if (Date.now() - selection.capturedAt > LAST_SELECTION_COPY_GRACE_MS) return '';
  return selection.text;
}

function createContextMenuRequestId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

export interface UsePtyOptions {
  /** Deterministic PTY session ID: makePtySessionId(projectId, scopeId, leafId). */
  sessionId: string;
  /** Pre-connected FrontendPty instance owned by the entity's PtySession store. */
  pty: FrontendPty;
  theme?: SessionTheme;
  mapShiftEnterToCtrlJ?: boolean;
  readOnly?: boolean;
  onActivity?: () => void;
  onFirstMessage?: (message: string) => void;
  onEnterPress?: (message: string) => void;
  onInterruptPress?: () => void;
  onPasteFromClipboard?: PasteFromClipboardHandler;
}

export interface UseTerminalReturn {
  focus: () => void;
  setTheme: (theme: SessionTheme) => void;
  sendInput: (data: string, options?: { track?: boolean }) => void;
}

export type PasteFromClipboardHandler = (helpers: {
  focus: UseTerminalReturn['focus'];
  sendInput: UseTerminalReturn['sendInput'];
}) => void;

/**
 * React hook that manages a full xterm.js terminal instance attached to
 * `containerRef`, wired to a PTY session via the deterministic `sessionId`.
 *
 * Each session owns a persistent FrontendPty (terminal + Canvas2D renderer)
 * for its full lifetime.  On unmount the terminal's ownedContainer is
 * reparented to the off-screen xterm host rather than disposed, so scrollback
 * is preserved across tab switches.
 *
 * For sessions pre-registered via PtySessionProvider the mount is effectively
 * synchronous (no await needed).  Standalone sessions (not pre-registered)
 * are auto-registered inside an async IIFE, awaiting the historical buffer
 * fetch before mounting.
 *
 * When inside a PaneSizingContextProvider the terminal is pre-resized to the pane's
 * current dimensions BEFORE being appended to the visible DOM, eliminating
 * the flash caused by a post-mount resize.
 */
export function usePty(
  options: UsePtyOptions,
  containerRef: React.RefObject<HTMLElement | null>
): UseTerminalReturn {
  const {
    sessionId,
    pty,
    theme,
    mapShiftEnterToCtrlJ,
    readOnly = false,
    onActivity,
    onFirstMessage,
    onEnterPress,
    onInterruptPress,
    onPasteFromClipboard,
  } = options;

  // Stable refs for callbacks so the effect doesn't re-run on every render.
  const onActivityRef = useRef(onActivity);
  onActivityRef.current = onActivity;
  const onFirstMessageRef = useRef(onFirstMessage);
  onFirstMessageRef.current = onFirstMessage;
  const onEnterPressRef = useRef(onEnterPress);
  onEnterPressRef.current = onEnterPress;
  const onInterruptPressRef = useRef(onInterruptPress);
  onInterruptPressRef.current = onInterruptPress;
  const onPasteFromClipboardRef = useRef(onPasteFromClipboard);
  onPasteFromClipboardRef.current = onPasteFromClipboard;
  const themeRef = useRef(theme);
  themeRef.current = theme;
  const readOnlyRef = useRef(readOnly);
  readOnlyRef.current = readOnly;

  // The per-pane controller owns PTY backend resizes (broadcast to ALL sessions)
  // and exposes an observable controllerDims box so this terminal can call
  // term.resize() reactively. PtyPane guarantees a context is always present by
  // self-provisioning a PaneDimensionProvider + PaneSizingContextProvider when
  // no ancestor provides one.
  const paneSizing = usePaneSizingContext();
  // Ref so the main effect (which only re-runs on sessionId change) always
  // accesses the latest context value without needing it as a dependency.
  const paneSizingRef = useRef(paneSizing);
  paneSizingRef.current = paneSizing;

  // Core xterm.js reference, kept alive across renders.
  const termRef = useRef<Terminal | null>(null);

  // First-message capture state.
  const firstMessageSentRef = useRef(false);
  const inputBufferRef = useRef('');

  // Tracks submitted user input while filtering terminal control traffic.
  const submittedInputBufferRef = useRef(new SubmittedInputBuffer());

  // Auto-copy on selection
  const autoCopyOnSelectionRef = useRef(false);
  const lastSelectionRef = useRef<{ text: string; capturedAt: number } | null>(null);
  const contextMenuRequestIdRef = useRef<string | null>(null);

  // ─── Helpers ───────────────────────────────────────────────────────────────

  // Calibrates the per-pane controller with the mounted terminal's real cell
  // metrics. The controller recomputes cols/rows, updates controllerDims, and
  // broadcasts runtime resize calls to ALL sessions. The MobX reaction below then
  // applies term.resize() to the visible grid.
  //
  // Cold-path retry: the terminal is opened off-DOM so xterm's font measurement
  // may not be populated yet on the first call — retries up to 5 times.
  //
  // Runs synchronously so the xterm DOM catches up in the same paint as the
  // new container size (ENG-1577).
  const measureAndResize = useCallback(
    (retries = 0) => {
      try {
        const term = termRef.current;
        if (!term) return;
        const pane = paneSizingRef.current;
        if (!pane) {
          log.warn('useTerminal: no PaneSizingContext — cannot calibrate', { sessionId });
          return;
        }

        const cell = getCellMetrics(term);
        if (!cell) {
          // Cold-path: terminal was opened off-DOM so xterm's font measurement
          // hasn't populated yet.  Retry up to 5 times to avoid an infinite loop.
          if (retries < 5) {
            setTimeout(() => measureAndResizeRef.current(retries + 1), 100);
          }
          return;
        }

        // Calibrate the controller with exact cell metrics.
        // The controller recomputes cols/rows, updates controllerDims, and
        // broadcasts runtime resize calls to all sessions. The MobX reaction below
        // applies term.resize() when controllerDims changes.
        pane.calibrateCell(cell.width, cell.height);
      } catch (e) {
        log.warn('useTerminal: measureAndResize failed', { sessionId, error: e });
      }
    },
    [sessionId]
  );

  // Stable ref so the retry setTimeout inside measureAndResize always calls
  // the latest version without creating a circular useCallback dependency.
  const measureAndResizeRef = useRef(measureAndResize);
  measureAndResizeRef.current = measureAndResize;

  const applyTheme = useCallback(
    (t?: SessionTheme) => {
      pty.setTheme(t);
    },
    [pty]
  );

  const setTheme = useCallback(
    (t: SessionTheme) => {
      applyTheme(t);
    },
    [applyTheme]
  );

  const focus = useCallback(() => {
    // Don't steal focus from an open modal — unless this terminal is rendered
    // inside it (e.g. the agent sign-in terminal).
    const dialog = document.activeElement?.closest('[role="dialog"]');
    if (dialog && !dialog.contains(containerRef.current)) return;
    termRef.current?.focus();
  }, [containerRef]);

  const copySelectionToClipboard = useCallback(() => {
    const selection =
      termRef.current?.getSelection() || getRecentSelection(lastSelectionRef.current);
    if (selection) {
      navigator.clipboard.writeText(selection).catch(() => {});
    }
  }, []);

  const sendInput = useCallback(
    (data: string, options?: { track?: boolean }) => {
      if (readOnlyRef.current) return;
      const shouldTrack = options?.track ?? true;
      if (shouldTrack) {
        const submittedMessages = submittedInputBufferRef.current.feed(data);
        for (const message of submittedMessages) {
          if (isRealTaskInput(message)) {
            onEnterPressRef.current?.(message);
          }
        }
      }
      pty.sendInput(data);
    },
    [pty]
  );

  useEffect(() => {
    pty.terminal.options.disableStdin = readOnly;
    return () => {
      pty.terminal.options.disableStdin = false;
    };
  }, [pty, readOnly]);

  const pasteFromClipboard = useCallback(() => {
    const customPasteFromClipboard = onPasteFromClipboardRef.current;
    if (customPasteFromClipboard) {
      customPasteFromClipboard({ focus, sendInput });
      return;
    }

    void (async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text) sendInput(text);
      } catch {
        // Clipboard read denied or unavailable.
      }
    })();
  }, [focus, sendInput]);

  // ─── Main effect: mount terminal once per sessionId ────────────────────────

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // ── Compute targetDims synchronously ─────────────────────────────────────
    // Reads the previous session's terminal cell metrics before overwriting
    // termRef. PaneSizingContext dimensions are also sampled here so the
    // pre-resize happens against the live pane dimensions.
    const pane = paneSizingRef.current;
    const prevCell = termRef.current ? getCellMetrics(termRef.current) : null;
    let targetDims: { cols: number; rows: number } | undefined;

    // Pane path: prefer the controller's current dims (already correct for the
    // pane size); fall back to a fresh pixel measurement if the controller
    // hasn't computed yet (e.g. very first mount before any calibration).
    if (pane) {
      targetDims = pane.getCurrentDimensions() ?? undefined;
      if (!targetDims && pane.containerRef.current && prevCell) {
        // Mirror the controller's padding exactly so the pre-mount dims match
        // what the controller will compute on first calibration.
        const measured = measureDimensions(
          pane.containerRef.current,
          prevCell.width,
          prevCell.height,
          0,
          TERMINAL_PADDING_PX,
          { bottom: pane.bottomPadding }
        );
        if (measured) targetDims = measured;
      }
    }

    // ── Mount ─────────────────────────────────────────────────────────────────
    // pty is pre-connected by PtySession before TerminalPane renders, so no
    // async work is needed here.
    const cleanups: (() => void)[] = [];

    {
      const frontendPty = pty;
      termRef.current = frontendPty.terminal;
      lastSelectionRef.current = null;

      // Apply current theme before mounting (in case it differs from the
      // theme the terminal was constructed with).
      frontendPty.setTheme(themeRef.current);

      // Mount: pre-resize then appendChild (flash-free).
      frontendPty.mount(container as HTMLElement, targetDims);

      // Always sync after mounting — targetDims may be stale if the pane was
      // resized while this session was off-screen.
      // Pane path: calibrate the controller cell metrics so it recomputes
      //   cols/rows and applies term.resize() via the controllerDims reaction.
      // Standalone path: measure locally and queue PTY resize.
      measureAndResize();

      // ── Load settings ──────────────────────────────────────────────────────
      let customFontFamily = '';
      void getAppSettingsClient()
        .then(async (client) => {
          const settings = (await client.get({
            key: 'terminal',
          })) as AppSettings['terminal'];
          return settings;
        })
        .then((terminalSettings) => {
          if (terminalSettings?.fontFamily) {
            customFontFamily = terminalSettings.fontFamily.trim();
            if (customFontFamily) {
              frontendPty.terminal.options.fontFamily = buildTerminalFontFamily(customFontFamily);
            }
          }
          frontendPty.terminal.options.fontSize =
            terminalSettings?.fontSize ?? TERMINAL_FONT_SIZE_DEFAULT;
          measureAndResize();
          autoCopyOnSelectionRef.current = terminalSettings?.autoCopyOnSelection ?? false;
          frontendPty.terminal.options.macOptionIsMeta = terminalSettings?.macOptionIsMeta ?? false;
        });

      // ── DECRQM xterm.js 6.0 bug workaround ────────────────────────────────
      const terminal = frontendPty.terminal;
      try {
        const parser = (
          terminal as unknown as {
            parser?: { registerCsiHandler?: (...args: unknown[]) => { dispose(): void } };
          }
        ).parser;
        if (parser?.registerCsiHandler) {
          const ansiDisp = parser.registerCsiHandler(
            { intermediates: '$', final: 'p' },
            (params: (number | number[])[]) => {
              const mode = (params[0] as number) ?? 0;
              sendInput(`\x1b[${mode};0$y`, { track: false });
              return true;
            }
          );
          const decDisp = parser.registerCsiHandler(
            { prefix: '?', intermediates: '$', final: 'p' },
            (params: (number | number[])[]) => {
              const mode = (params[0] as number) ?? 0;
              sendInput(`\x1b[?${mode};0$y`, { track: false });
              return true;
            }
          );
          cleanups.push(
            () => ansiDisp.dispose(),
            () => decDisp.dispose()
          );
        }
      } catch (err) {
        log.warn('useTerminal: failed to register DECRQM workaround', { error: err });
      }

      // ── Keyboard shortcuts ─────────────────────────────────────────────────
      terminal.attachCustomKeyEventHandler((event: KeyboardEvent) => {
        // Ignore keys while a modal is open — unless this terminal is the one
        // rendered inside it (e.g. the agent sign-in terminal).
        const dialog = document.querySelector('[role="dialog"]');
        if (dialog && !dialog.contains(container)) return false;

        if (
          shouldCopySelectionFromTerminal(
            event,
            IS_MAC_PLATFORM,
            terminal.hasSelection(),
            getRecentSelection(lastSelectionRef.current) !== ''
          )
        ) {
          event.preventDefault();
          event.stopImmediatePropagation();
          event.stopPropagation();
          copySelectionToClipboard();
          return false;
        }

        if (shouldPasteToTerminal(event, IS_MAC_PLATFORM, IS_WINDOWS_PLATFORM)) {
          event.preventDefault();
          event.stopImmediatePropagation();
          event.stopPropagation();
          pasteFromClipboard();
          return false;
        }

        if (mapShiftEnterToCtrlJ && shouldMapShiftEnterToCtrlJ(event)) {
          event.preventDefault();
          event.stopImmediatePropagation();
          event.stopPropagation();
          sendInput(CTRL_J_ASCII);
          return false;
        }

        if (shouldKillLineFromTerminal(event, IS_MAC_PLATFORM)) {
          event.preventDefault();
          event.stopImmediatePropagation();
          event.stopPropagation();
          sendInput(CTRL_U_ASCII);
          return false;
        }

        if (shouldHandleInterruptFromTerminal(event)) {
          onInterruptPressRef.current?.();
          return true;
        }

        if (
          IS_MAC_PLATFORM &&
          event.metaKey &&
          !event.ctrlKey &&
          !event.shiftKey &&
          !event.altKey
        ) {
          if (event.key === 'ArrowLeft') {
            event.preventDefault();
            event.stopImmediatePropagation();
            event.stopPropagation();
            sendInput('\x01');
            return false;
          }
          if (event.key === 'ArrowRight') {
            event.preventDefault();
            event.stopImmediatePropagation();
            event.stopPropagation();
            sendInput('\x05');
            return false;
          }
        }

        return true;
      });

      // ── Handle terminal input ──────────────────────────────────────────────
      const handleTerminalInput = (data: string) => {
        onActivityRef.current?.();

        if (!data) return;

        // First-message capture
        if (!firstMessageSentRef.current && onFirstMessageRef.current) {
          inputBufferRef.current += data;
          const newlineIndex = inputBufferRef.current.indexOf('\r');
          if (newlineIndex !== -1) {
            const message = inputBufferRef.current.slice(0, newlineIndex);
            onFirstMessageRef.current(message);
            firstMessageSentRef.current = true;
          }
        }

        sendInput(data);
      };

      const inputDisposable = terminal.onData((data) => handleTerminalInput(data));
      cleanups.push(() => inputDisposable.dispose());

      // ── Auto-copy on selection ─────────────────────────────────────────────
      let selectionDebounceTimer: ReturnType<typeof setTimeout> | null = null;
      const selectionDisposable = terminal.onSelectionChange(() => {
        const selection = terminal.getSelection();
        if (selection) {
          lastSelectionRef.current = { text: selection, capturedAt: Date.now() };
        }

        if (!autoCopyOnSelectionRef.current) return;
        if (!terminal.hasSelection()) return;
        if (selectionDebounceTimer) clearTimeout(selectionDebounceTimer);
        selectionDebounceTimer = setTimeout(() => {
          if (terminal.hasSelection()) {
            copySelectionToClipboard();
          }
        }, 150);
      });
      cleanups.push(() => {
        selectionDisposable.dispose();
        if (selectionDebounceTimer) clearTimeout(selectionDebounceTimer);
      });

      // ── Native context menu ────────────────────────────────────────────────
      const handleContextMenuMouseDown = (event: MouseEvent) => {
        if (event.button !== 2) return;
        event.preventDefault();
        event.stopPropagation();
      };
      const handleContextMenu = (event: MouseEvent) => {
        event.preventDefault();
        event.stopPropagation();

        const requestId = createContextMenuRequestId();
        contextMenuRequestIdRef.current = requestId;
        const selectionText =
          terminal.getSelection() || getRecentSelection(lastSelectionRef.current);
        const linkText = getTerminalContextLink(terminal, event);
        void getHostClient().then((client) =>
          client.showTerminalContextMenu({
            requestId,
            selectionText,
            linkText,
            x: event.clientX,
            y: event.clientY,
          })
        );
      };
      let disposedContextMenu = false;
      let offTerminalContextMenuAction: (() => void) | undefined;
      void getHostClient().then(async (client) => {
        const unsubscribe = await client.events.subscribe(undefined, {
          onEvent: (event) => {
            if (
              event.type !== 'terminal-context-menu-action' ||
              event.requestId !== contextMenuRequestIdRef.current
            ) {
              return;
            }
            contextMenuRequestIdRef.current = null;

            if (event.action === 'paste') pasteFromClipboard();
            else if (event.action === 'select-all') terminal.selectAll();
            else if (event.action === 'clear') frontendPty.clear();
          },
          onGap: () => {},
        });
        if (disposedContextMenu) unsubscribe();
        else offTerminalContextMenuAction = unsubscribe;
      });
      frontendPty.ownedContainer.addEventListener('mousedown', handleContextMenuMouseDown, true);
      frontendPty.ownedContainer.addEventListener('contextmenu', handleContextMenu);
      cleanups.push(() => {
        disposedContextMenu = true;
        offTerminalContextMenuAction?.();
        contextMenuRequestIdRef.current = null;
        frontendPty.ownedContainer.removeEventListener(
          'mousedown',
          handleContextMenuMouseDown,
          true
        );
        frontendPty.ownedContainer.removeEventListener('contextmenu', handleContextMenu);
      });

      // ── Font / setting change events ───────────────────────────────────────
      const handleFontChange = (e: Event) => {
        const detail = (e as CustomEvent<{ fontFamily?: string; fontSize?: number }>).detail;
        if (detail?.fontFamily !== undefined) {
          customFontFamily = detail.fontFamily.trim();
          terminal.options.fontFamily = buildTerminalFontFamily(customFontFamily);
        }
        if (detail?.fontSize !== undefined) {
          terminal.options.fontSize = detail.fontSize;
        }
        measureAndResize();
      };
      const handleAutoCopyChange = (e: Event) => {
        const detail = (e as CustomEvent<{ autoCopyOnSelection?: boolean }>).detail;
        autoCopyOnSelectionRef.current = detail?.autoCopyOnSelection ?? false;
      };
      const handleMacOptionIsMetaChange = (e: Event) => {
        const detail = (e as CustomEvent<{ macOptionIsMeta?: boolean }>).detail;
        terminal.options.macOptionIsMeta = detail?.macOptionIsMeta ?? false;
      };
      window.addEventListener('terminal-font-changed', handleFontChange);
      window.addEventListener('terminal-auto-copy-changed', handleAutoCopyChange);
      window.addEventListener('terminal-mac-option-is-meta-changed', handleMacOptionIsMetaChange);
      cleanups.push(
        () => window.removeEventListener('terminal-font-changed', handleFontChange),
        () => window.removeEventListener('terminal-auto-copy-changed', handleAutoCopyChange),
        () =>
          window.removeEventListener(
            'terminal-mac-option-is-meta-changed',
            handleMacOptionIsMetaChange
          )
      );

      // ── Resize trigger ────────────────────────────────────────────────────
      // React to controllerDims — the observable box updated by the per-pane
      // resize controller when pane pixel dimensions or cell size changes.
      // The controller owns PTY backend broadcasts; here we only apply
      // term.resize() to keep the visible xterm grid in sync. The reaction
      // fires synchronously within the ResizeObserver → MobX action → reaction
      // chain, preserving the "resize before next paint" guarantee (ENG-1577).
      const paneAtMount = paneSizingRef.current;
      if (paneAtMount) {
        const disposeReaction = reaction(
          () => paneAtMount.controllerDims.get(),
          (dims) => {
            if (!dims) return;
            const term = termRef.current;
            if (!term) return;
            if (term.cols !== dims.cols || term.rows !== dims.rows) {
              term.resize(dims.cols, dims.rows);
            }
          }
        );
        cleanups.push(disposeReaction);
      }
    }

    // ── Cleanup ───────────────────────────────────────────────────────────────
    return () => {
      // controllerDims reaction and other cleanups run BEFORE unmount —
      // preserving the invariant that they are torn down before the
      // ownedContainer is reparented off-screen.
      for (const fn of cleanups) {
        try {
          fn();
        } catch {}
      }
      // Return terminal's ownedContainer to the off-screen host only if this
      // React host still owns it. A terminal session can be reparented into a
      // different surface before this cleanup runs; in that case, unmounting
      // here would steal the xterm DOM back from the new owner.
      if (container.contains(pty.ownedContainer)) {
        pty.unmount();
      }
      termRef.current = null;
      firstMessageSentRef.current = false;
      inputBufferRef.current = '';
      submittedInputBufferRef.current = new SubmittedInputBuffer();
    };
    // oxlint-disable-next-line react/exhaustive-deps
  }, [sessionId, pty]); // Re-run only when the session changes

  // ── Theme update (after initial mount) ──────────────────────────────────────
  useEffect(() => {
    applyTheme(theme);
  }, [theme, applyTheme]);

  return { focus, setTheme, sendInput };
}
