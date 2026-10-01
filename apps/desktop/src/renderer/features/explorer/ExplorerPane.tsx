import { PanelsTopLeft, Plus, SquareTerminal } from "lucide-react";
import { Component, lazy, Suspense, useEffect, useState } from "react";
import type { ComponentProps, ComponentType, ReactNode } from "react";

import { Button } from "@renderer/components/ui/button";
import { isMac } from "@renderer/lib/platform";
import { useActiveProject } from "@renderer/state/projects";
import { useActiveTab, useExplorer } from "@renderer/state/explorer";
import type { ExplorerTab } from "@shared/types";
import type { Project } from "@shared/types";

import { BrowserTab } from "./BrowserTab";
import { EmptyState } from "@text-to-cad/ui/navigation";
import { DrawingTab } from "./DrawingTab";
import { FileTab } from "./FileTab";
import { EXPLORER_TABPANEL_ID, TabStrip, explorerTabDomId } from "./TabStrip";
import { focusTabBody } from "./focus";
import { loadTerminal, preloadTerminal } from "./load-terminal";
import type { ReviewTab as ReviewTabBody } from "./ReviewTab";
import type { TerminalTab as TerminalTabBody } from "./TerminalTab";
import { desktopCadConnectionForTab } from "./adapters/cadRuntime";

// The review draws with Monaco (~9.6 MB of the window's first chunk when it was
// imported here) and the terminal with xterm; both load with the first tab of
// their kind, the way the drawing surface and the file renderers already do. The
// terminal's is also fetched at idle and on a new-terminal request (`./load-terminal`).
//
// A chunk that fails to load (a dropped fetch, an update replacing the files under a
// running window) leaves `lazy` rejected for good, so each tab kind is drawn through
// `LazyTab`: a boundary where the failure lands, and a Try again that builds a new `lazy`.
const ReviewTab = lazyTab<ComponentProps<typeof ReviewTabBody>>(() => import("./ReviewTab").then((module) => ({ default: module.ReviewTab })));
const TerminalTab = lazyTab<ComponentProps<typeof TerminalTabBody>>(() => loadTerminal().then((module) => ({ default: module.TerminalTab })));

/** A lazy component that can be replaced with a fresh one after its import failed. */
function lazyTab<P extends object>(load: () => Promise<{ default: ComponentType<P> }>) {
  // The import's rejection is marked, so the boundary can tell a chunk that did not load from
  // a body that threw while rendering: only the first is cured by fetching the chunk again.
  const marked = () => load().catch((error: unknown) => { throw new ChunkLoadError(error); });
  let current = lazy(marked);
  return { get: () => current, retry: () => { current = lazy(marked); } };
}

class ChunkLoadError extends Error {
  constructor(cause: unknown) {
    super("A tab's code did not load", { cause });
  }
}

class TabBoundary extends Component<
  { children: ReactNode; failed: (retry: () => void) => ReactNode; broken: (error: Error) => ReactNode; onRetry: () => void },
  { error: Error | null }
> {
  override state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: unknown) {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }
  override render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return error instanceof ChunkLoadError ? this.props.failed(() => this.props.onRetry()) : this.props.broken(error);
  }
}

/**
 * A lazy tab body with its fallback and the place its chunk's failure is drawn. Without the
 * boundary a rejected import unmounts the whole window (`main.tsx` has no boundary of its own).
 */
function LazyTab<P extends object>({ tab, props, opening, what }: {
  tab: ReturnType<typeof lazyTab<P>>; props: P; opening: string; what: string;
}) {
  const [attempt, setAttempt] = useState(0);
  // Held in state: the component is replaced by a retry, never made during a render.
  const [Body, setBody] = useState(() => tab.get());
  return (
    <TabBoundary
      failed={(retry) => (
        <div role="alert">
          <EmptyState action={<Button onClick={retry} size="sm" variant="secondary">Try again</Button>}
            description={`The code for the ${what} did not load.`} icon={SquareTerminal} title={`Could not open the ${what}`} tone="warn" />
        </div>
      )}
      // A body that threw: fetching its chunk again would throw again, so there is no Try again.
      broken={(error) => (
        <div role="alert">
          <EmptyState description={error.message} icon={SquareTerminal} title="This tab hit an error" tone="warn" />
        </div>
      )}
      key={attempt}
      onRetry={() => { tab.retry(); setBody(tab.get()); setAttempt((count) => count + 1); }}
    >
      <Suspense fallback={<TabLoading label={opening} />}>
        <Body {...props} />
      </Suspense>
    </TabBoundary>
  );
}

/**
 * The explorer: one tab strip and whatever the selected tab renders.
 *
 * Every tab kind is kept mounted only while it is selected. That is the
 * cheaper half of a real trade-off — a webview and an xterm each cost a
 * process and a canvas, and eight background tabs of them is a slow window —
 * and the state that would otherwise be lost is kept where it belongs instead:
 * the pty and live browser page in main, the browser's URL on the tab, the file's draft in
 * the tab's own component, the tree's geometry in the store.
 */
export function ExplorerPane() {
  const project = useActiveProject();
  const tabs = useExplorer((state) => state.tabs);
  const loadError = useExplorer(state => state.loadError);
  const ready = useExplorer((state) => state.ready);
  const open = useExplorer((state) => state.open);
  const active = useActiveTab();

  useIdlePreload();

  // `Shell` does not mount this pane without a session — the strip belongs to
  // a session and there is none — so this is the type's guard rather than a
  // state a person can reach. There is deliberately no "No session" view: an
  // explorer with nothing to explore is a pane worth its width to nobody.
  if (!project) {
    return null;
  }

  return (
    <Frame>
      <TabStrip />
      {/* The strip's active tab names this panel through aria-controls; the pair lives in TabStrip. */}
      <div className="min-h-0 flex-1" id={EXPLORER_TABPANEL_ID} role="tabpanel" aria-labelledby={active ? explorerTabDomId(active.id) : undefined}>
        {loadError ? <EmptyState title="Could not restore tabs" description={loadError} icon={PanelsTopLeft}
          action={<Button onClick={() => { const state = useExplorer.getState(); void state.bindSession(state.sessionId, state.projectId, state.root); }}>Try again</Button>} /> : active ? (
          <TabBody key={active.id} project={project} tab={active} />
        ) : (
          <EmptyState
            action={
              <Button className="h-7 gap-1.5 text-xs" disabled={!ready} onClick={() => open("file")} size="sm" variant="secondary">
                <Plus className="size-3.5" />
                Open a file
              </Button>
            }
            description={
              ready && tabs.length === 0
                ? "Files, reviews, browsers, terminals and drawings all open here, in one strip."
                : "Restoring…"
            }
            icon={PanelsTopLeft}
            title="Nothing open"
          />
        )}
      </div>
    </Frame>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return <div className="flex h-full min-h-0 flex-col border-l">{children}</div>;
}

function TabBody({ tab, project }: {
  tab: ExplorerTab; project: Project;
}) {
  switch (tab.kind) {
    case "file":
      return (
        <FileTab
          sessionId={tab.sessionId}
          panel={tab.panel}
          path={tab.path}
          project={project}
          root={tab.root}
          tabId={tab.id}
          cadConnection={desktopCadConnectionForTab(tab)}
        />
      );
    case "review":
      return (
        <LazyTab opening="Opening review…" tab={ReviewTab} what="review"
          props={{ project, scope: tab.scope, sessionId: tab.sessionId, tabId: tab.id }} />
      );
    case "drawing":
      return <DrawingTab sessionId={tab.sessionId} project={project} root={tab.root} tabId={tab.id} title={tab.title} />;
    case "browser":
      return <BrowserTab sessionId={tab.sessionId} projectId={project.id} root={tab.root} tabId={tab.id} url={tab.url} />;
    case "terminal":
      return (
        <LazyTab opening="Opening terminal…" tab={TerminalTab} what="terminal"
          props={{ sessionId: tab.sessionId, cwd: tab.cwd, project, ptyId: tab.ptyId, readOnly: tab.readOnly, agent: tab.agent, tabId: tab.id }} />
      );
  }
}

/**
 * A lazy tab's first frame, drawn as the Markdown renderer's "Opening source…" is.
 *
 * `data-focus-pending` is the body telling `./focus` it is not there yet: a
 * tab asked for while its chunk loads is waited for, not given up on for the
 * strip tab, or the first terminal a window opens never takes the keyboard.
 */
function TabLoading({ label }: { label: string }) {
  return <div className="p-4 text-xs text-muted-foreground" data-focus-pending>{label}</div>;
}

/** The terminal's chunk, fetched once the window has painted and has nothing better to do. */
function useIdlePreload() {
  useEffect(() => {
    if (typeof window.requestIdleCallback !== "function") return;
    const handle = window.requestIdleCallback(preloadTerminal);
    return () => window.cancelIdleCallback(handle);
  }, []);
}

/**
 * Every chord here is the person asking for a tab, so the keyboard follows it
 * (`./focus`): into the body, or onto the tab. Left where it was, the focus of
 * a body the chord just unmounted — an editor, a tree row — fell to the page.
 */
function focusOpened(tab: ExplorerTab | null) {
  if (tab) focusTabBody(tab.id);
}

/**
 * The strip's keyboard.
 *
 * On the window rather than on the strip, because the chords have to work
 * while the focus is inside a tab's body — an editor, a terminal, a webview —
 * which is where it usually is. `Cmd/Ctrl+W` is intercepted before the menu's
 * default close-window accelerator: with tabs open it means "close this tab",
 * and only an empty strip lets it close the window.
 *
 * The "new tab" chords are here too, and they are the same ones the `+`
 * menu prints beside its rows (`src/renderer/lib/shortcuts.ts` is the table
 * both read).
 *
 * Mounted by `Shell`, not by the pane: the pane is not rendered while it is
 * collapsed, which is how every session starts, and a chord that asks for a
 * tab is exactly what has to work then (`open` reveals the pane).
 *
 * What runs when:
 *   - No session: nothing; every chord falls through to the menu.
 *   - Open-a-tab chords (`Ctrl+\``, `Mod+T`, `Mod+Shift+R/B/D`) run whether the
 *     pane is collapsed or not, because `open` reveals it.
 *   - Collapsed pane: `Mod+W` and `Mod+1..9` act on tabs nobody can see, so they
 *     fall through to the menu (`Mod+W` closes the window).
 *   - `event.repeat` is swallowed: a held chord opens or closes one tab, not a
 *     dozen. A held `Mod+W` is swallowed even after the last tab is gone, so it
 *     does not go on to close the window.
 *   - On Windows and Linux the plain `Ctrl` chords (`Ctrl+T`, `Ctrl+W`,
 *     `Ctrl+1..9`) are skipped inside `[data-terminal-body]`, where they are the
 *     shell's; `Ctrl+Shift` chords and `Ctrl+\`` still run there.
 */
export function useExplorerShortcuts() {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const { tabs, activeId, closeActive, selectIndex, open, sessionId } = useExplorer.getState();
      // No session, no strip: the chords are left to the menu (Cmd+W closes the window).
      if (sessionId === null) {
        return;
      }

      // `⌃\`` is Control on macOS as well: it is the chord a person already
      // has in their fingers for a terminal, and it is the same one on the
      // machine they came from.
      // The physical key, as the mac explorer chord is: on a layout where the backtick is a
      // dead key, `event.key` is "Dead" and only `event.code` still says which key it was.
      if (event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey && (event.code === "Backquote" || event.key === "`")) {
        event.preventDefault();
        if (!event.repeat) {
          preloadTerminal();
          focusOpened(open("terminal"));
        }
        return;
      }

      const modifier = isMac ? event.metaKey : event.ctrlKey;
      if (!modifier || event.altKey) {
        return;
      }
      const key = event.key.toLowerCase();
      if (event.shiftKey) {
        // Secondary tab kinds. `Mod+B` is the sidebar,
        // so `Mod+Shift+B` had to stay clear of it — Shell's handler drops
        // anything with Shift held for exactly this reason.
        const kind = key === "r" ? "review" : key === "b" ? "browser" : key === "d" ? "drawing" : null;
        if (kind) {
          event.preventDefault();
          if (!event.repeat) focusOpened(open(kind));
        }
        return;
      }
      // Control is the shell's on Windows and Linux: Ctrl+W deletes a word, Ctrl+T
      // transposes, Ctrl+1..9 are typed. With the focus in a terminal the terminal
      // keeps them — it forwards Ctrl+K/C/V itself (`TerminalTab`) — and the strip's
      // plain chords wait for the focus to leave. Cmd is no shell's key, so macOS keeps them.
      // The Shift chords above are no shell's, so they run from a terminal too and this waits.
      if (!isMac && event.target instanceof Element && event.target.closest("[data-terminal-body]")) {
        return;
      }

      if (key === "t") {
        event.preventDefault();
        if (!event.repeat) focusOpened(open("file"));
        return;
      }
      // The chords above open a tab, and opening reveals the pane. Close and pick act on tabs
      // the person cannot see while the explorer is collapsed, so they are left to the menu
      // (Cmd+W closes the window, as it did before there was a strip): closing a hidden tab
      // would kill its shell, and picking one would change what the next reveal shows.
      if (useExplorer.getState().collapsed) {
        return;
      }
      // A held key repeats: it is swallowed, not acted on again. Holding Cmd+T would open
      // tabs by the dozen, and holding Cmd+W would close them all and then, with none left,
      // fall through to the menu's Close and close the window.
      if (key === "w" && (activeId || event.repeat)) {
        event.preventDefault();
        if (!event.repeat) closeActive();
        return;
      }
      if (/^[1-9]$/.test(event.key) && tabs.length > 0) {
        event.preventDefault();
        // 9 is the last tab, the way browsers do it — otherwise the ninth
        // shortcut is dead in every strip with fewer than nine tabs.
        const index = event.key === "9" ? tabs.length : Number(event.key);
        selectIndex(index);
        focusOpened(tabs[index - 1] ?? null);
      }
    };
    // Capture: a terminal and Monaco both swallow keys on the bubble phase.
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);
}
