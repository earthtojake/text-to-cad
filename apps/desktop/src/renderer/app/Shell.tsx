import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { PANE_HOMES, TABBABLE } from "@renderer/app/pane-focus";
import { PaneSeparator } from "@renderer/app/PaneSeparator";
import { ExplorerPane, useExplorerShortcuts } from "@renderer/features/explorer/ExplorerPane";
import { SessionPane } from "@renderer/features/session/SessionPane";
import { Sidebar } from "@renderer/features/sidebar/Sidebar";
import { maxWidthOf, resolvePanes } from "@renderer/lib/panes";
import type { SidePane } from "@renderer/lib/panes";
import { isPrimaryModifier } from "@renderer/lib/platform";
import { runUiCommand } from "@renderer/state/bridge";
import { useExplorer } from "@renderer/state/explorer";
import { useSettings } from "@renderer/state/settings";
import { PANE_LIMITS } from "@shared/types";

/**
 * Three panes: projects, the session, the explorer (plan §3).
 *
 * A plain flex row, in pixels. The sidebar and the explorer are each
 * `width: Npx`, the session takes what is left with a `min-width` floor, and
 * two separators size the side panes. There is no panel library: the shell
 * needs one behaviour per pane and a library that keeps its own collapse
 * state alongside ours is how the person ended up with a pane off screen and
 * no toggle anywhere to bring it back.
 *
 * **One source of truth per side pane**, `{ collapsed, width }` — the
 * sidebar's in `settings.layout`, the explorer's per session in
 * `state/explorer.ts`. Everything here is derived from those two pairs: which
 * panes are rendered, where each toggle is drawn (a collapsed pane is not in
 * the document, so its toggle can only be the other one), and which pane
 * makes room for the macOS traffic lights.
 *
 * **A drag past a minimum collapses the pane.** The separator stops at the
 * minimum and, 40px further (`PANE_LIMITS.overshoot`), writes `collapsed`
 * and keeps the width — so the pane is gone, its toggle is on screen, and the
 * toggle brings it back the size it was. Nothing snaps back and nothing
 * disappears without a control to undo it.
 *
 * **The session never collapses.** Its 320px is a floor the separators stop
 * against. When the window cannot hold all three minimums the explorer gives
 * way first and the sidebar second, by collapsing — so the person is left
 * with two toggles rather than a session pushed off the window.
 *
 * **Landmarks.** The session is the `main`; the sidebar an `aside` and the
 * explorer a named `section`, which also scopes each pane's own `<header>`
 * (two unscoped ones were two banners). F6 and Shift+F6 move focus between
 * the panes on screen (`usePaneCycling`).
 *
 * **No session, no explorer.** An unsubmitted draft owns no tabs: neither the pane nor its separator is
 * rendered, the session has the window, and the toggle in `SessionHeader`,
 * the palette's command and `Mod+Alt+B` all have nothing to act on.
 */
export function Shell() {
  const layout = useSettings((state) => state.settings?.layout);
  const setLayout = useSettings((state) => state.setLayout);
  const rowRef = useRef<HTMLDivElement | null>(null);

  useShellShortcuts();
  useExplorerShortcuts();
  usePaneCycling();

  // The explorer belongs to a session, and is closed until something opens
  // it (`state/explorer.ts`). Its width is per session as well.
  const hasSession = useExplorer(state => state.sessionId !== null);
  const explorerCollapsed = useExplorer((state) => state.collapsed);
  const explorerWidth = useExplorer((state) => state.width);
  const setExplorerWidth = useExplorer((state) => state.setWidth);
  const setExplorerCollapsed = useExplorer((state) => state.setCollapsed);

  const sidebarCollapsed = layout?.sidebarCollapsed ?? false;
  const storedSidebarWidth = layout?.sidebarWidth ?? PANE_LIMITS.sidebar.default;

  // The row's own width, measured. Every clamp is against this: a pane's
  // maximum is what the window has left after the session's floor.
  //
  // The window's width to start with, not zero: the row is the window, and a
  // first frame laid out against zero draws both side panes at their minimums
  // and then jumps to their real widths when the observer fires.
  const [rowWidth, setRowWidth] = useState(() => window.innerWidth);
  useLayoutEffect(() => {
    const element = rowRef.current;
    if (!element) {
      return;
    }
    setRowWidth(element.getBoundingClientRect().width);
    const observer = new ResizeObserver(() => {
      setRowWidth(element.getBoundingClientRect().width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // A drag's width, while it is happening. Held here rather than written to
  // the stores on every pointer move: the sidebar's width is a row in sqlite,
  // and a drag is two hundred of them. The gesture's end writes it once.
  const [dragging, setDragging] = useState<{ pane: SidePane; width: number } | null>(null);
  const sidebarWidth = dragging?.pane === "sidebar" ? dragging.width : storedSidebarWidth;
  const paneWidth = dragging?.pane === "explorer" ? dragging.width : explorerWidth;

  const resolved = resolvePanes({
    width: rowWidth,
    sidebar: { collapsed: sidebarCollapsed, width: sidebarWidth },
    explorer: hasSession ? { collapsed: explorerCollapsed, width: paneWidth } : null,
  });

  // A window too narrow for the three minimums closes a pane rather than
  // overflowing, and that has to reach the *state*: a pane merely not drawn
  // would leave its toggle looking pressed with nothing to press.
  //
  // Every render, guarded, rather than on a dependency: what has to be true
  // afterwards is "the state agrees with what fits", and the two writes are
  // no-ops once it does.
  useEffect(() => {
    if (resolved.collapse.includes("explorer") && !explorerCollapsed) {
      setExplorerCollapsed(true);
    }
    if (resolved.collapse.includes("sidebar") && !sidebarCollapsed) {
      void setLayout({ sidebarCollapsed: true });
    }
  });

  useFocusSurvivesCollapse(sidebarCollapsed, hasSession && explorerCollapsed);

  // Which pane makes room for the macOS traffic lights (`--titlebar-inset`,
  // globals.css): the sidebar's strip while it is on screen, the session's
  // title bar once it is not. Derived from the one flag, because the flag is
  // now the only way the sidebar can be off screen.
  const leftmost = sidebarCollapsed ? "session" : "sidebar";

  return (
    <div
      className="h-screen w-screen overflow-hidden bg-background text-foreground"
      data-leftmost={leftmost}
      data-shell
    >
      <div className="flex h-full w-full" ref={rowRef}>
        {resolved.sidebar === null ? null : (
          <>
            <aside
              aria-label="Sidebar"
              className="shrink-0 overflow-hidden bg-sidebar text-sidebar-foreground"
              data-panel
              data-testid="sidebar"
              id="sidebar"
              style={{ width: resolved.sidebar }}
            >
              <Sidebar />
            </aside>
            <PaneSeparator
              max={maxWidthOf("sidebar", { width: rowWidth, other: resolved.explorer })}
              min={PANE_LIMITS.sidebar.min}
              onCollapse={() => void setLayout({ sidebarCollapsed: true })}
              onCommit={(width) => void setLayout({ sidebarWidth: width })}
              onDrag={(width) => setDragging({ pane: "sidebar", width })}
              onRelease={() => setDragging(null)}
              pane="sidebar"
              width={resolved.sidebar}
            />
          </>
        )}

        <main
          className="min-w-0 flex-1 bg-background"
          data-panel
          data-testid="session"
          id="session"
          style={{ minWidth: PANE_LIMITS.session.min }}
        >
          <SessionPane />
        </main>

        {resolved.explorer === null ? null : (
          <>
            <PaneSeparator
              max={maxWidthOf("explorer", { width: rowWidth, other: resolved.sidebar })}
              min={PANE_LIMITS.explorer.min}
              onCollapse={() => setExplorerCollapsed(true)}
              onCommit={(width) => setExplorerWidth(width)}
              onDrag={(width) => setDragging({ pane: "explorer", width })}
              onRelease={() => setDragging(null)}
              pane="explorer"
              width={resolved.explorer}
            />
            <section
              aria-label="Explorer"
              className="shrink-0 overflow-hidden bg-background"
              data-panel
              data-testid="explorer"
              id="explorer"
              style={{ width: resolved.explorer }}
            >
              <ExplorerPane />
            </section>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * Cmd/Ctrl+B and Cmd/Ctrl+Alt+B for the panes, Cmd/Ctrl+[ and Cmd/Ctrl+] for
 * the history — bound here as well as in the app menu, because the menu's
 * accelerator is the one that works with focus in a webview and this one
 * works when the menu is hidden. Both ends at the same commands.
 * `toggle-explorer` is inert without a session: the store refuses a
 * preference it has nowhere to file.
 */
function useShellShortcuts(): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isPrimaryModifier(event) || event.shiftKey) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "b") {
        event.preventDefault();
        const opening = event.altKey && useExplorer.getState().sessionId !== null && useExplorer.getState().collapsed;
        runUiCommand({ command: event.altKey ? "toggle-explorer" : "toggle-sidebar" });
        // The chord that opens the explorer takes the keyboard into it — its strip's tab, else
        // `+` — as the chords that open a tab do (`features/explorer/focus.ts`).
        if (opening) {
          window.requestAnimationFrame(() => {
            const pane = document.getElementById("explorer");
            pane?.querySelector<HTMLElement>(`${PANE_HOMES.explorer}, [data-new-tab] button`)?.focus();
          });
        }
        return;
      }
      if (event.altKey) {
        return;
      }
      if (key === "[") {
        event.preventDefault();
        runUiCommand({ command: "navigate-back" });
      } else if (key === "]") {
        event.preventDefault();
        runUiCommand({ command: "navigate-forward" });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}

/** The panes F6 visits, in order; a collapsed one is not in the document and is skipped. */
const PANE_IDS = ["sidebar", "session", "explorer"] as const;

/**
 * F6 and Shift+F6: the next and the previous pane, the way a browser's F6
 * moves between its toolbar and the page. Without it the only way from the
 * explorer back to the sidebar was every Tab stop in between — and none at
 * all out of a terminal. Focus returns to where it last was in a pane, while
 * that element is still there, else to the pane's home.
 *
 * On the window's capture phase, before an editor or a terminal takes the
 * key; renderer-only, like Escape (`lib/shortcuts.ts`).
 */
function usePaneCycling(): void {
  const last = useRef<Partial<Record<(typeof PANE_IDS)[number], HTMLElement>>>({});
  useEffect(() => {
    const paneOf = (node: EventTarget | null) =>
      node instanceof Element ? PANE_IDS.find((id) => document.getElementById(id)?.contains(node)) : undefined;
    const onFocusIn = (event: FocusEvent) => {
      const pane = paneOf(event.target);
      if (pane && event.target instanceof HTMLElement) last.current[pane] = event.target;
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "F6" || event.metaKey || event.ctrlKey || event.altKey) return;
      const panes = PANE_IDS.filter((id) => document.getElementById(id));
      if (panes.length === 0) return;
      event.preventDefault();
      event.stopPropagation();
      const current = paneOf(document.activeElement);
      const at = current ? panes.indexOf(current) : -1;
      const step = event.shiftKey ? -1 : 1;
      const next = panes[(at + step + panes.length) % panes.length] ?? panes[0]!;
      const pane = document.getElementById(next)!;
      const remembered = last.current[next];
      const target =
        (remembered?.isConnected && pane.contains(remembered) ? remembered : null) ??
        pane.querySelector<HTMLElement>(PANE_HOMES[next]) ??
        pane.querySelector<HTMLElement>(TABBABLE);
      target?.focus();
    };
    document.addEventListener("focusin", onFocusIn);
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("focusin", onFocusIn);
      window.removeEventListener("keydown", onKeyDown, true);
    };
  }, []);
}

/**
 * A pane that closes with focus in it (Cmd+B, Cmd+Alt+B, its own toggle, a drag past the
 * minimum) takes that focus out of the document, and it fell to the page. It goes to the pane's
 * toggle instead — the same control, now in the session's title bar — so the next Cmd+B, or
 * Enter, brings the pane back from where the person is.
 */
function useFocusSurvivesCollapse(sidebarCollapsed: boolean, explorerCollapsed: boolean): void {
  const lastPane = useRef<string | null>(null);
  useEffect(() => {
    const note = (event: Event) => {
      const target = event.target instanceof Element ? event.target : null;
      // A pane's separator is outside the pane (it sits between two), but it is that pane's: Enter
      // on it closes the pane, and the toggle is where focus belongs after.
      const separated = target?.closest<HTMLElement>("[data-separator]")?.dataset.separator ?? null;
      lastPane.current = separated ?? (target ? (PANE_IDS.find((id) => document.getElementById(id)?.contains(target)) ?? null) : null);
    };
    document.addEventListener("focusin", note);
    document.addEventListener("pointerdown", note, true);
    return () => {
      document.removeEventListener("focusin", note);
      document.removeEventListener("pointerdown", note, true);
    };
  }, []);
  useEffect(() => {
    if (sidebarCollapsed) handToToggle(lastPane.current, "sidebar", "Toggle sidebar");
  }, [sidebarCollapsed]);
  useEffect(() => {
    if (explorerCollapsed) handToToggle(lastPane.current, "explorer", "Toggle explorer");
  }, [explorerCollapsed]);
}

/** Focus the session's copy of a pane's toggle, when focus was last in that pane and is lost. */
function handToToggle(lastPane: string | null, pane: string, toggle: string): void {
  const lost = !document.activeElement || document.activeElement === document.body;
  if (lastPane !== pane || !lost) return;
  document.querySelector<HTMLElement>(`#session [aria-label="${toggle}"]`)?.focus();
}
