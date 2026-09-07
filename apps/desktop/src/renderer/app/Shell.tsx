import { useCallback, useEffect, useRef } from "react";
import type { RefObject } from "react";
import type { GroupImperativeHandle, Layout, LayoutChangedMeta, PanelImperativeHandle } from "react-resizable-panels";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@renderer/components/ui/resizable";
import { ExplorerPane } from "@renderer/features/explorer/ExplorerPane";
import { SessionPane } from "@renderer/features/session/SessionPane";
import { Sidebar } from "@renderer/features/sidebar/Sidebar";
import { isMac } from "@renderer/lib/platform";
import { runUiCommand } from "@renderer/state/bridge";
import { useExplorer } from "@renderer/state/explorer";
import { useActiveProject } from "@renderer/state/projects";
import { useSettings } from "@renderer/state/settings";
import { PANE_LIMITS } from "@shared/types";

/** `ResizableHandle` is a one-pixel line (components/ui/resizable.tsx). */
const SEPARATOR_PX = 1;

/**
 * Three panes: projects, the session, the explorer (plan §3).
 *
 * Widths are pixels, Codex's way: the sidebar is 230px whatever the window
 * does, the session column is 560px by default and never narrower (its
 * transcript is a 720px column with room to breathe), and the explorer takes
 * what is left. The two fixed ones are persisted in settings so the window
 * comes back the way it was left; the explorer's width is a consequence, not
 * a preference.
 *
 * **The sidebar and the explorer collapse; the session never does.** It is
 * not `collapsible` at all, so its 560px is a floor the explorer's divider
 * stops against rather than a threshold past which the pane disappears. The
 * only thing that used to take the session away was the explorer's fullscreen,
 * and that is gone.
 *
 * **No project, no explorer.** The pane is a view of a directory, and with
 * none bound there is no directory: the panel and its separator are not
 * rendered, the session has the window, and the toggle in `SessionHeader`,
 * the palette's command and `Mod+Alt+B` all have nothing to act on.
 */
export function Shell() {
  const layout = useSettings((state) => state.settings?.layout);
  const setLayout = useSettings((state) => state.setLayout);
  const sidebarRef = useRef<PanelImperativeHandle | null>(null);
  const explorerRef = useRef<PanelImperativeHandle | null>(null);
  const groupRef = useRef<GroupImperativeHandle | null>(null);
  const groupElementRef = useRef<HTMLDivElement | null>(null);

  useShellShortcuts();

  // The explorer belongs to a project. Without one the group is two panels
  // wide and there is no control that would open a third.
  const hasProject = useActiveProject() !== null;
  // The explorer is closed until something opens it, and its state belongs to
  // the project rather than to the app (`state/explorer.ts`).
  const explorerClosed = useExplorer((state) => state.collapsed);

  const sidebarCollapsed = layout?.sidebarCollapsed ?? false;
  const explorerCollapsed = !hasProject || explorerClosed;

  // Which pane is leftmost decides who makes room for the macOS traffic
  // lights (`--titlebar-inset`, globals.css): the sidebar's header normally,
  // and the session's title bar once the sidebar is hidden.
  const leftmost = sidebarCollapsed ? "session" : "sidebar";

  // The collapsed flags are state, not a one-off gesture: the menu, the
  // keyboard and a drag to zero all write the same flag, and the panels follow
  // it. Doing this imperatively is what react-resizable-panels asks for.
  usePanelCollapsed(sidebarRef, sidebarCollapsed);
  usePanelCollapsed(explorerRef, explorerCollapsed);

  // The library keeps shares, so a window that shrinks takes width from
  // every pane in proportion — and the sidebar came back from 1440 to 1280
  // at 180px. The preference is pixels: on every change of the group's own
  // width the whole layout is set again from the two fixed widths, and the
  // explorer absorbs the difference, which is the whole contract of this
  // layout. One `setLayout` rather than a resize per panel: resizing the
  // session on its own took the difference from the sidebar and collapsed it.
  const sidebarWidth = layout?.sidebarWidth ?? PANE_LIMITS.sidebar.default;
  const sessionWidth = layout?.sessionWidth ?? PANE_LIMITS.session.default;
  const applyLayout = useCallback(() => {
    const element = groupElementRef.current;
    if (!element) {
      return;
    }
    // Next frame, not now: the library's own observer re-derives every
    // panel's constraints for a new size, and a layout set before that is
    // validated against the old ones — a 230px sidebar in a window grown
    // to 1680 read as under its minimum and collapsed. The same frame's
    // delay lets a collapse or an expand land before the shares are set.
    requestAnimationFrame(() => {
      const width = element.getBoundingClientRect().width;
      if (width <= 0) {
        return;
      }
      // Shares are of the width the panels divide: the group less its
      // separators, which are two with the explorer and one without. Against
      // the whole width the sidebar lands a pixel short.
      const shares = paneShares({
        width: width - separatorsFor(hasProject) * SEPARATOR_PX,
        sidebarWidth,
        sessionWidth,
        sidebarCollapsed,
        explorerCollapsed,
      });
      // A share for a panel that is not mounted is a share the library has
      // nowhere to put. The explorer's is zero in that case anyway, so the
      // other two already add up to a hundred without it.
      groupRef.current?.setLayout(
        hasProject ? shares : { sidebar: shares.sidebar, session: shares.session },
      );
    });
  }, [hasProject, sidebarCollapsed, explorerCollapsed, sidebarWidth, sessionWidth]);

  useEffect(() => {
    const element = groupElementRef.current;
    if (!element) {
      return;
    }
    let previous = element.getBoundingClientRect().width;
    const observer = new ResizeObserver(() => {
      const width = element.getBoundingClientRect().width;
      if (width === previous) {
        return;
      }
      previous = width;
      applyLayout();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [applyLayout]);

  // A pane that comes back from collapsed — or from a project arriving and
  // making a third panel — is restored by the library to "its most recent
  // size", which is a share of some earlier width; the preference is
  // reapplied.
  useEffect(() => {
    applyLayout();
  }, [applyLayout]);

  const onLayoutChanged = (next: Layout, meta: LayoutChangedMeta) => {
    // Only a drag or a resize keypress is worth writing: mount and the
    // programmatic collapse above also fire here, and persisting those would
    // overwrite the user's sizes with whatever the collapse produced.
    if (!meta.isUserInteraction) {
      return;
    }
    // The library reports shares; the preference is pixels, so the group's
    // own width turns one into the other. A pane at zero is collapsed, and a
    // collapse is recorded by its flag, not by a width of nothing.
    const width =
      (groupElementRef.current?.getBoundingClientRect().width ?? 0) -
      separatorsFor(hasProject) * SEPARATOR_PX;
    if (width <= 0) {
      return;
    }
    const patch: { sidebarWidth?: number; sessionWidth?: number } = {};
    const sidebar = Math.round(((next.sidebar ?? 0) / 100) * width);
    const session = Math.round(((next.session ?? 0) / 100) * width);
    if (sidebar > 0) {
      patch.sidebarWidth = sidebar;
    }
    if (session > 0) {
      patch.sessionWidth = session;
    }
    if (Object.keys(patch).length > 0) {
      void setLayout(patch);
    }
  };

  return (
    <div
      className="h-screen w-screen overflow-hidden bg-background text-foreground"
      data-leftmost={leftmost}
      data-shell
    >
      <ResizablePanelGroup
        elementRef={groupElementRef}
        groupRef={groupRef}
        id="shell"
        onLayoutChanged={onLayoutChanged}
        orientation="horizontal"
      >
        <ResizablePanel
          id="sidebar"
          panelRef={sidebarRef}
          defaultSize={layout?.sidebarWidth ?? PANE_LIMITS.sidebar.default}
          minSize={PANE_LIMITS.sidebar.min}
          maxSize={PANE_LIMITS.sidebar.max}
          collapsible
          collapsedSize={0}
          className="bg-sidebar text-sidebar-foreground"
        >
          <Sidebar />
        </ResizablePanel>

        <ResizableHandle />

        {/*
          Deliberately not `collapsible`: the session is the app. Without the
          flag the library reads `minSize` as a floor the explorer's divider
          stops against, rather than as the point past which the pane is
          collapsed to nothing.
        */}
        <ResizablePanel
          id="session"
          defaultSize={layout?.sessionWidth ?? PANE_LIMITS.session.default}
          minSize={PANE_LIMITS.session.min}
          className="bg-background"
        >
          <SessionPane />
        </ResizablePanel>

        {hasProject ? (
          <>
            <ResizableHandle />

            <ResizablePanel
              id="explorer"
              panelRef={explorerRef}
              minSize={PANE_LIMITS.explorer.min}
              collapsible
              collapsedSize={0}
              className="bg-background"
            >
              <ExplorerPane />
            </ResizablePanel>
          </>
        ) : null}
      </ResizablePanelGroup>
    </div>
  );
}

/** One separator between every pair of panes; the explorer is optional. */
function separatorsFor(hasProject: boolean): number {
  return hasProject ? 2 : 1;
}

/** How long a panel is given to become known to its group, in frames. */
const PANEL_READY_FRAMES = 60;

/**
 * Hold one panel at `collapsed`, waiting for the group to have measured it.
 *
 * `collapse()` and `expand()` throw `Panel constraints not found` when a
 * panel has mounted but its group has not derived its constraints yet — the
 * group does that from a resize observation, which is a frame or two after
 * React's commit. That window is exactly the one the explorer arrives in: a
 * project is chosen, the third panel mounts, and the effect that opens it
 * runs immediately. Unhandled, the throw takes the whole renderer down and
 * leaves an empty window (found by `tests/e2e/explorer.spec.ts`'s reload).
 *
 * So it is retried, frame by frame, rather than swallowed: the flag is the
 * state and the panel has to end up matching it. The bound is there because a
 * panel that is never going to be found should not spin forever.
 */
function usePanelCollapsed(
  ref: RefObject<PanelImperativeHandle | null>,
  collapsed: boolean,
): void {
  useEffect(() => {
    let frame = 0;
    let attempts = 0;
    const apply = () => {
      const panel = ref.current;
      if (!panel) {
        return;
      }
      try {
        if (collapsed) {
          panel.collapse();
        } else {
          panel.expand();
        }
      } catch {
        attempts += 1;
        if (attempts < PANEL_READY_FRAMES) {
          frame = requestAnimationFrame(apply);
        }
      }
    };
    apply();
    return () => cancelAnimationFrame(frame);
  }, [ref, collapsed]);
}

/**
 * The three panes' shares of a group `width` px wide, from the two fixed
 * widths. Collapsed panes are zero; the session takes what the explorer
 * would have when the explorer is closed — which is also what happens when
 * there is no project and no explorer panel at all; and the explorer is never
 * squeezed below its floor — the session gives way first, since the window has
 * a minimum that keeps the sidebar and the explorer's floor in reach.
 */
export function paneShares({
  width,
  sidebarWidth,
  sessionWidth,
  sidebarCollapsed,
  explorerCollapsed,
}: {
  width: number;
  sidebarWidth: number;
  sessionWidth: number;
  sidebarCollapsed: boolean;
  explorerCollapsed: boolean;
}): { sidebar: number; session: number; explorer: number } {
  const sidebar = sidebarCollapsed ? 0 : Math.min(sidebarWidth, PANE_LIMITS.sidebar.max);
  let explorer = explorerCollapsed ? 0 : Math.max(PANE_LIMITS.explorer.min, width - sidebar - sessionWidth);
  let session = width - sidebar - explorer;
  if (session < PANE_LIMITS.session.min && !explorerCollapsed) {
    session = Math.min(PANE_LIMITS.session.min, width - sidebar);
    explorer = Math.max(0, width - sidebar - session);
  }
  const share = (px: number) => (px / width) * 100;
  return { sidebar: share(sidebar), session: share(session), explorer: share(explorer) };
}

/**
 * Cmd/Ctrl+B and Cmd/Ctrl+Alt+B, bound here as well as in the app menu —
 * the menu's accelerator is the one that works with focus in a webview,
 * this one works when the menu is hidden — and both end at the same
 * command. `toggle-explorer` is inert without a project: the store refuses
 * a preference it has nowhere to file.
 */
function useShellShortcuts(): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const modifier = isMac ? event.metaKey : event.ctrlKey;
      if (!modifier || event.shiftKey || event.key.toLowerCase() !== "b") {
        return;
      }
      event.preventDefault();
      runUiCommand({ command: event.altKey ? "toggle-explorer" : "toggle-sidebar" });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
