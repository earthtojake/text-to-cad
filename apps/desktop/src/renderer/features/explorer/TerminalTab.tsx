import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Terminal } from "@xterm/xterm";
import { SquareTerminal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import "@xterm/xterm/css/xterm.css";

import { Button } from "@renderer/components/ui/button";
import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { useExplorer } from "@renderer/state/explorer";
import type { Project } from "@shared/types";

import { EmptyState } from "./EmptyState";

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

export function TerminalTab({
  tabId,
  project,
  ptyId,
  cwd,
  readOnly,
}: {
  tabId: string;
  project: Project;
  ptyId: string | null;
  cwd: string | null;
  readOnly: boolean;
}) {
  const update = useExplorer((state) => state.update);
  const mode = useResolvedTheme();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exited, setExited] = useState<number | null>(null);

  // Spawn once, when the tab has no pty yet. `starting` guards React's double
  // effect invocation in development, which would otherwise leave an orphan
  // shell running for every terminal tab opened.
  const starting = useRef(false);
  useEffect(() => {
    if (ptyId || starting.current) {
      return;
    }
    starting.current = true;
    void window.hardcore.terminal
      .create({ projectId: project.id, ...(cwd ? { cwd } : {}) })
      .then((info) => update(tabId, { ptyId: info.id }))
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : String(caught));
      })
      .finally(() => {
        starting.current = false;
      });
  }, [ptyId, project.id, cwd, tabId, update]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !ptyId) {
      return;
    }

    const term = new Terminal({
      allowProposedApi: true,
      cursorBlink: !readOnly,
      disableStdin: readOnly,
      fontFamily:
        'ui-monospace, "SF Mono", SFMono-Regular, Menlo, Monaco, "Cascadia Mono", Consolas, monospace',
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

    const fit = new FitAddon();
    term.loadAddon(fit);
    term.loadAddon(
      new WebLinksAddon((_event, uri) => {
        // A URL printed by a build belongs in a browser, not in a webview
        // whose chrome this pane does not have.
        void window.hardcore.shell.openExternal({ url: uri }).catch(() => {});
      }),
    );
    term.open(host);

    const push = () => {
      fit.fit();
      void window.hardcore.terminal
        .resize({ id: ptyId, cols: term.cols, rows: term.rows })
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

    const offData = window.hardcore.on("terminal.data", (event) => {
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
    void window.hardcore.terminal
      .attach({ id: ptyId })
      .then((attached) => {
        if (!attached) {
          setError("That shell is no longer running.");
          return;
        }
        if (attached.scrollback) {
          term.write(attached.scrollback);
        }
        snapshotSeq = attached.seq;
        for (const chunk of pending) {
          if (chunk.seq > attached.seq) {
            term.write(chunk.data);
          }
        }
        pending = [];
        if (attached.info.exitCode !== null) {
          setExited(attached.info.exitCode);
        }
        push();
      })
      .catch(() => {});
    const offExit = window.hardcore.on("terminal.exit", (event) => {
      if (event.id === ptyId) {
        setExited(event.exitCode);
      }
    });

    if (!readOnly) {
      term.onData((data) => {
        void window.hardcore.terminal.write({ id: ptyId, data }).catch(() => {});
      });
    }

    // Cmd/Ctrl+K clears, as it does in every terminal on this platform; the
    // copy/paste chords are handled here too because xterm swallows keys
    // before the menu's accelerators see them.
    term.attachCustomKeyEventHandler((event) => {
      if (event.type !== "keydown") {
        return true;
      }
      const modifier = event.metaKey || event.ctrlKey;
      if (modifier && event.key.toLowerCase() === "k") {
        term.clear();
        return false;
      }
      if (modifier && event.key.toLowerCase() === "c" && term.hasSelection()) {
        void navigator.clipboard.writeText(term.getSelection()).catch(() => {});
        term.clearSelection();
        return false;
      }
      if (modifier && event.key.toLowerCase() === "v") {
        void navigator.clipboard.readText().then((text) => {
          if (text) {
            void window.hardcore.terminal.write({ id: ptyId, data: text }).catch(() => {});
          }
        });
        return false;
      }
      return true;
    });

    // The pane is resizable and the strip can expand, so the pty's size has to
    // follow the element rather than the window.
    const observer = new ResizeObserver(() => push());
    observer.observe(host);
    push();
    if (!readOnly) {
      term.focus();
    }

    return () => {
      observer.disconnect();
      offData();
      offExit();
      term.dispose();
      termRef.current = null;
    };
  }, [ptyId, readOnly, mode]);

  if (error) {
    return (
      <EmptyState
        action={
          <Button
            className="h-7 text-xs"
            onClick={() => {
              setError(null);
              update(tabId, { ptyId: null });
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
      <div className="min-h-0 flex-1 overflow-hidden px-2 pt-2" data-selectable ref={hostRef} />
      <div className="flex h-6 shrink-0 items-center gap-2 border-t px-3 text-[11px] text-muted-foreground">
        <span className="truncate">{cwd ?? project.path}</span>
        {readOnly ? <span className="shrink-0 rounded-sm bg-muted px-1">agent</span> : null}
        <span className="flex-1" />
        {exited === null ? null : (
          <span className="shrink-0">
            exited {exited}
            <button
              className="ml-2 underline underline-offset-2 hover:text-foreground"
              onClick={() => {
                setExited(null);
                update(tabId, { ptyId: null });
              }}
              type="button"
            >
              restart
            </button>
          </span>
        )}
      </div>
    </div>
  );
}
