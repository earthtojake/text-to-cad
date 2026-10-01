import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Terminal } from "@xterm/xterm";
import { createPromptContext } from "@text-to-cad/core/prompt";
import { createDesktopPromptContext } from "./host/promptContext";
import { useSessions } from "@renderer/state/sessions";
import { toast } from "sonner";
import { Eraser, SquareTerminal, MessageSquarePlus } from "lucide-react";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import "@xterm/xterm/css/xterm.css";

import { Button } from "@renderer/components/ui/button";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { terminalPromptRoot } from "@renderer/lib/terminal-workspace";
import { useExplorer, updateSessionTab } from "@renderer/state/explorer";
import { errorMessage } from "@shared/ipc/errors";
import { isTerminalReply } from "@shared/terminal-replies";
import type { Project } from "@shared/types";

import { EmptyState } from "@text-to-cad/ui/navigation";

import { claimFocus, holdFocusClaim } from "./focus";

/**
 * xterm.js over a pty in main.
 *
 * The pty outlives the component. A tab that is switched away from unmounts
 * this xterm, and main keeps producing and buffering output; coming back
 * reattaches to the same `ptyId` and replays the scrollback, so a build that
 * ran while the person was reading a diff is all there. That is why the id is
 * on the tab and not in a ref.
 *
 * Everything about the terminal lives in one effect keyed on `ptyId`. xterm is
 * an imperative widget with a DOM of its own: splitting its creation, its
 * listeners and its disposal across effects is how a second terminal ends up
 * attached to the same element.
 */

/** The app's tokens, as xterm's theme wants them — hex, and a full ANSI set. */
function themeFor(mode: "light" | "dark") {
  return mode === "dark"
    ? {
        background: "#0a0a0a",
        foreground: "#fafafa",
        cursor: "#fafafa",
        cursorAccent: "#0a0a0a",
        selectionBackground: "#404040",
        black: "#262626",
        red: "#f87171",
        green: "#4ade80",
        yellow: "#fbbf24",
        blue: "#60a5fa",
        magenta: "#c084fc",
        cyan: "#22d3ee",
        white: "#e5e5e5",
        brightBlack: "#737373",
        brightRed: "#fca5a5",
        brightGreen: "#86efac",
        brightYellow: "#fcd34d",
        brightBlue: "#93c5fd",
        brightMagenta: "#d8b4fe",
        brightCyan: "#67e8f9",
        brightWhite: "#fafafa",
      }
    : {
        background: "#ffffff",
        foreground: "#0a0a0a",
        cursor: "#0a0a0a",
        cursorAccent: "#ffffff",
        selectionBackground: "#e5e5e5",
        black: "#171717",
        red: "#dc2626",
        green: "#16a34a",
        yellow: "#ca8a04",
        blue: "#2563eb",
        magenta: "#9333ea",
        cyan: "#0891b2",
        white: "#e5e5e5",
        brightBlack: "#737373",
        brightRed: "#ef4444",
        brightGreen: "#22c55e",
        brightYellow: "#eab308",
        brightBlue: "#3b82f6",
        brightMagenta: "#a855f7",
        brightCyan: "#06b6d4",
        brightWhite: "#0a0a0a",
      };
}

/** Before Settings has written `--font-mono`, and in a test with no stylesheet. */
const FALLBACK_FONT = 'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, "Cascadia Mono", Consolas, monospace';

/** The Code font the person chose, as the rest of the app's code reads it. */
function codeFont(): string {
  return getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim() || FALLBACK_FONT;
}

/**
 * Tab-focus mode, as Monaco's (Ctrl+Shift+M, `lib/shortcuts.ts`): while it is
 * on, Tab and Shift+Tab move focus out of the terminal instead of reaching the
 * shell. Off by default — completion is what Tab is for in a shell — and one
 * switch for every terminal, as Monaco's is one for every editor. Without it a
 * terminal is a keyboard trap: xterm takes every key, Escape included, which
 * belongs to whatever runs in it.
 */
let tabMovesFocus = false;
const tabModeListeners = new Set<() => void>();
function toggleTabMovesFocus() {
  tabMovesFocus = !tabMovesFocus;
  for (const listener of tabModeListeners) listener();
}
function useTabMovesFocus(): boolean {
  return useSyncExternalStore(
    (listener) => {
      tabModeListeners.add(listener);
      return () => tabModeListeners.delete(listener);
    },
    () => tabMovesFocus,
  );
}

/** The chord, as `event` has it: Control and Shift, on every platform, like Monaco's on macOS. */
export function isTabFocusChord(event: KeyboardEvent): boolean {
  return event.ctrlKey && event.shiftKey && !event.metaKey && !event.altKey && event.key.toLowerCase() === "m";
}

/** Shells being spawned, by tab, until the tab has their id (or the spawn failed). */
const spawning = new Map<string, Promise<unknown>>();

export function TerminalTab({
  tabId,
  sessionId,
  project,
  ptyId,
  cwd,
  readOnly,
  agent = false,
}: {
  tabId: string;
  sessionId: string;
  project: Project;
  ptyId: string | null;
  cwd: string | null;
  readOnly: boolean;
  /** Opened by the agent: a respawned shell gets the runtime launchers on PATH again. */
  agent?: boolean;
}) {
  const update = useExplorer((state) => state.update);
  const mode = useResolvedTheme();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState("");
  /** What the banner over the footer says: the shell ended, or the pty could not be attached to or written. */
  const [notice, setNotice] = useState<string | null>(null);
  const setExited = (code: number | null) => setNotice(code === null ? null : `The shell exited (code ${code}).`);
  const tabMoves = useTabMovesFocus();
  // Focus is taken when the person opened or picked this tab (`./focus`), never
  // on every mount: a session switch, Back or a theme change remounts it too.
  useEffect(() => (readOnly ? undefined : holdFocusClaim(tabId, () => termRef.current?.focus())), [tabId, readOnly]);
  // A rebuild of this same terminal (the theme changed) keeps focus it had.
  const hadFocus = useRef(false);

  const sessions = useSessions(state => state.sessions);
  const promptRoot = useMemo(() => terminalPromptRoot(project, cwd, sessions.filter(session => session.id === sessionId)), [sessionId, cwd, project, sessions]);
  const prompt = useMemo(() => createDesktopPromptContext(project.id, promptRoot, JSON.stringify(['desktop', project.id, promptRoot]), sessionId), [sessionId, project.id, promptRoot]);
  const addSelection = () => {
    if (!selection) return;
    void prompt.deliver(createPromptContext([{ id: 'terminal-selection', kind: 'text',
      text: `Terminal output from ${cwd ?? project.path} (${tabId}):\n${selection}` }])).then(result => {
      if (result.status === 'added') toast.success('Terminal selection added to prompt');
      else if (result.status === 'failed' || result.status === 'cancelled') toast.error(result.message ?? 'Could not add terminal selection.');
    }).catch(error => toast.error(String(error)));
  };

  // Spawn once, when the tab has no pty yet. The spawn is `spawning`'s, by tab and not by
  // instance: React's double effect in development and a body that unmounts and mounts again
  // (a tab picked away and back) while `create` is still in flight would each start a shell
  // for the one tab, and the loser would be an orphan counting toward the agent's 16.
  useEffect(() => {
    if (ptyId) {
      return;
    }
    let spawn = spawning.get(tabId);
    if (!spawn) {
      spawn = window.textToCad.terminal
        .create({ sessionId, projectId: project.id, ...(cwd ? { cwd } : {}), ...(agent ? { agent } : {}) })
        // A shell can finish spawning after the person changes sessions.
        .then((info) => updateSessionTab(sessionId, tabId, { ptyId: info.id, cwd: info.cwd })
          .catch(() => window.textToCad.terminal.kill({ id: info.id, sessionId }).catch(() => {})))
        .finally(() => {
          spawning.delete(tabId);
        });
      spawning.set(tabId, spawn);
    }
    void spawn.catch((caught: unknown) => {
      setError(errorMessage(caught));
    });
  }, [ptyId, sessionId, project.id, cwd, agent, tabId]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !ptyId) {
      return;
    }

    const term = new Terminal({
      allowProposedApi: true,
      cursorBlink: !readOnly,
      disableStdin: readOnly,
      fontFamily: codeFont(),
      fontSize: 12,
      lineHeight: 1.35,
      // Main keeps 512 KB for replay; this is what a person can scroll back
      // through in the widget itself.
      scrollback: 5000,
      theme: themeFor(mode),
      // The pane has no room for a widget-drawn scrollbar next to the app's.
      scrollOnUserInput: true,
    });
    termRef.current = term;
    setSelection("");
    term.onSelectionChange(() => setSelection(term.getSelection().slice(0, 128000)));

    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(
      new WebLinksAddon((_event, uri) => {
        // A URL printed by a build belongs in a browser, not in a webview
        // whose chrome this pane does not have.
        void window.textToCad.shell.openExternal({ url: uri }).catch(() => {});
      }),
    );
    term.open(host);

    const push = () => {
      fit.fit();
      void window.textToCad.terminal
        .resize({ id: ptyId, sessionId, cols: term.cols, rows: term.rows })
        .catch(() => {});
    };

    /**
     * The live stream and the scrollback overlap, and the overlap has to be
     * dropped.
     *
     * The subscription is opened before the snapshot is asked for — the other
     * order loses whatever the shell writes in between — so chunks arriving
     * while the snapshot is in flight are also *in* that snapshot. They are
     * held here until it lands, then replayed from where it ended; after that
     * every chunk goes straight through. Without this the shell's startup is
     * written twice, which is what a duplicated `nvm` warning in the first
     * screenshot of this pane turned out to be.
     */
    let snapshotSeq: number | null = null;
    let pending: { seq: number; data: string }[] = [];
    /**
     * True while the scrollback is being parsed. A query in it (`ESC[6n`, a
     * device-attributes request) was asked of a widget that is long gone;
     * xterm answers it again on replay, and that answer, sent on, arrives at
     * whatever runs now as if it had been typed. It is dropped here.
     */
    let replaying = false;
    /** The shell is gone: a write that fails now is the shell's end, not a second problem to name. */
    let exited = false;

    const offData = window.textToCad.on("terminal.data", (event) => {
      if (event.id !== ptyId) {
        return;
      }
      if (snapshotSeq === null) {
        pending.push({ seq: event.seq, data: event.data });
      } else if (event.seq > snapshotSeq) {
        term.write(event.data);
      }
    });

    // Attach: whatever the shell wrote while this tab was closed.
    void window.textToCad.terminal
      .attach({ id: ptyId, sessionId })
      .then((attached) => {
        if (!attached) {
          setError("That shell is no longer running.");
          return;
        }
        if (attached.scrollback) {
          replaying = true;
          term.write(attached.scrollback, () => {
            replaying = false;
          });
        }
        snapshotSeq = attached.seq;
        for (const chunk of pending) {
          if (chunk.seq > attached.seq) {
            term.write(chunk.data);
          }
        }
        pending = [];
        if (attached.info.exitCode !== null) {
          exited = true;
          setExited(attached.info.exitCode);
        }
        push();
      })
      .catch((caught: unknown) => setNotice(errorMessage(caught)));
    const offExit = window.textToCad.on("terminal.exit", (event) => {
      if (event.id === ptyId) {
        exited = true;
        setExited(event.exitCode);
      }
    });

    if (!readOnly) {
      term.onData((data) => {
        if (replaying && isTerminalReply(data)) {
          return;
        }
        void window.textToCad.terminal.write({ id: ptyId, sessionId, data }).catch((caught: unknown) => {
          // The write that races the shell's exit rejects too: the exit sentence is the true one.
          if (!exited) setNotice(errorMessage(caught));
        });
      });
    }

    // Cmd/Ctrl+K belongs to the command palette, app-wide: it is passed over
    // here (not written to the shell, not handled) so the palette's window
    // listener and the menu accelerator see it exactly as they do anywhere
    // else. Clearing is the footer's Clear button. Copy is handled
    // here because xterm swallows keys before the menu's accelerators see it.
    term.attachCustomKeyEventHandler((event) => {
      if (event.type !== "keydown") {
        return true;
      }
      if (isTabFocusChord(event)) {
        toggleTabMovesFocus();
        return false;
      }
      // Not handled, so not prevented: the browser moves focus.
      if (event.key === "Tab" && tabMovesFocus && !event.ctrlKey && !event.metaKey && !event.altKey) {
        return false;
      }
      const modifier = event.metaKey || event.ctrlKey;
      if (modifier && event.key.toLowerCase() === "k") {
        return false;
      }
      if (modifier && event.key.toLowerCase() === "c" && term.hasSelection()) {
        void navigator.clipboard.writeText(term.getSelection()).catch(() => {});
        term.clearSelection();
        return false;
      }
      // Paste is xterm's: passed over (not prevented) so the browser's paste
      // event reaches xterm's own listener, which wraps the text in bracketed-
      // paste markers when the shell asked for them. Writing the clipboard here
      // as well would run a pasted command twice, once unbracketed. Returning
      // false also keeps Ctrl+V from reaching the shell as ^V.
      if (modifier && event.key.toLowerCase() === "v") {
        return false;
      }
      return true;
    });

    // The pane is resizable and the strip can expand, so the pty's size has to
    // follow the element rather than the window.
    const observer = new ResizeObserver(() => push());
    observer.observe(host);
    // Settings' Code font is `--font-mono` on <html> (`use-appearance.ts`),
    // written in an effect that runs after this one; follow it rather than
    // rebuild the terminal, which would replay the whole scrollback.
    const fontObserver = new MutationObserver(() => {
      const family = codeFont();
      if (term.options.fontFamily !== family) {
        term.options.fontFamily = family;
        push();
      }
    });
    fontObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["style"] });
    push();
    if (!readOnly && (claimFocus(tabId) || hadFocus.current)) {
      term.focus();
    }

    return () => {
      hadFocus.current = host.contains(document.activeElement);
      observer.disconnect();
      fontObserver.disconnect();
      offData();
      offExit();
      term.dispose();
      termRef.current = null;
    };
    // `tabId` is fixed for the component's life: the body is keyed on it.
  }, [ptyId, sessionId, readOnly, mode, tabId]);

  // A new shell for this tab. The old pty is killed first: main keeps an
  // exited pty's scrollback (up to 512 KB) until its tab lets go of the id,
  // and a tab that only forgot it would leave that behind on every restart.
  const restart = () => {
    if (ptyId) void window.textToCad.terminal.kill({ id: ptyId, sessionId }).catch(() => {});
    update(tabId, { ptyId: null });
  };

  if (error) {
    return (
      <EmptyState
        action={
          <Button
            className="h-7 text-xs"
            onClick={() => {
              setError(null);
              restart();
            }}
            size="sm"
            variant="secondary"
          >
            Try again
          </Button>
        }
        description={error}
        icon={SquareTerminal}
        title="No shell"
        tone="warn"
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="min-h-0 flex-1 overflow-hidden px-2 pt-2" data-selectable data-terminal-body ref={hostRef} />
      {notice === null ? null : (
        <div className="flex items-center gap-2 border-t bg-muted/60 px-3 py-1.5 text-xs text-foreground" role="status">
          <span className="min-w-0 flex-1 whitespace-pre-wrap">{notice}</span>
          <Button className="h-6 shrink-0 text-xs" onClick={() => { setNotice(null); restart(); }} size="sm" variant="secondary">Try again</Button>
        </div>
      )}
      <div className="flex h-6 shrink-0 items-center gap-2 border-t px-3 text-[11px] text-muted-foreground">
        <span className="truncate">{cwd ?? project.path}</span>
        {agent ? <span className="shrink-0 rounded-sm bg-muted px-1">agent</span> : null}
        <span className="flex-1" />
        {/* Said when it changes, since the key that changes it draws nothing else. */}
        <span className="shrink-0" role="status">{tabMoves ? "Tab moves focus" : ""}</span>
        <button type="button" className="inline-flex h-5 shrink-0 items-center gap-1 hover:text-foreground"
          onClick={() => { termRef.current?.clear(); termRef.current?.focus(); }}><Eraser className="size-3" />Clear</button>
        <button type="button" className="inline-flex h-5 shrink-0 items-center gap-1 hover:text-foreground disabled:opacity-40"
          disabled={!selection} onClick={addSelection}><MessageSquarePlus className="size-3" />Add to prompt</button>
      </div>
    </div>
  );
}
