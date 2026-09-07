import { useCallback, useEffect, useRef } from "react";
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
 * a preference. The sidebar and the explorer collapse; the session never does —
 * it is the app — and with the explorer collapsed it fills the window.
 */
export function Shell() {
  const layout = useSettings((state) => state.settings?.layout);
  const setLayout = useSettings((state) => state.setLayout);
  const sidebarRef = useRef<PanelImperativeHandle | null>(null);
  const explorerRef = useRef<PanelImperativeHandle | null>(null);
  const sessionRef = useRef<PanelImperativeHandle | null>(null);
  const groupRef = useRef<GroupImperativeHandle | null>(null);
  const groupElementRef = useRef<HTMLDivElement | null>(null);

  useShellShortcuts();

  // The explorer's expand affordance (the strip's far-right control, plan §2)
  // is a *view*, not a preference: it collapses the other two panes without
  // writing their collapsed flags, so leaving it restores what was there.
  const expanded = useExplorer((state) => state.expanded);
  // The explorer is closed until something opens it, and its state belongs to
  // the project rather than to the app (`state/explorer.ts`).
  const explorerClosed = useExplorer((state) => state.collapsed);

  const sidebarCollapsed = expanded || (layout?.sidebarCollapsed ?? false);
  const explorerCollapsed = !expanded && explorerClosed;
  const sessionCollapsed = expanded;

  // Which pane is leftmost decides who makes room for the macOS traffic
  // lights (`--titlebar-inset`, globals.css): normally the sidebar's header,
  // but the session's title bar when the sidebar is hidden and the explorer's
  // strip when it has the whole window.
  const leftmost = expanded ? "explorer" : sidebarCollapsed ? "session" : "sidebar";

  // The collapsed flags are state, not a one-off gesture: the menu, the
  // keyboard and a drag to zero all write the same flag, and the panels follow
  // it. Doing this imperatively is what react-resizable-panels asks for.
  useEffect(() => {
    const panel = sidebarRef.current;
    if (!panel) {
      return;
    }
    if (sidebarCollapsed) {
      panel.collapse();
    } else {
      panel.expand();
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    const panel = explorerRef.current;
    if (!panel) {
      return;
    }
    if (explorerCollapsed) {
      panel.collapse();
    } else {
      panel.expand();
    }
  }, [explorerCollapsed]);

  useEffect(() => {
    const panel = sessionRef.current;
    if (!panel) {
      return;
    }
    if (sessionCollapsed) {
      panel.collapse();
    } else {
      panel.expand();
    }
  }, [sessionCollapsed]);

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
    if (!element || expanded) {
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
      // Shares are of the width the panels divide: the group less its two
      // one-pixel separators. Against the whole width the sidebar lands a
      // pixel short.
      groupRef.current?.setLayout(
        paneShares({ width: width - 2 * SEPARATOR_PX, sidebarWidth, sessionWidth, sidebarCollapsed, explorerCollapsed }),
      );
    });
  }, [expanded, sidebarCollapsed, explorerCollapsed, sidebarWidth, sessionWidth]);

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

  // A pane that comes back from collapsed — or the whole shape coming back
  // from expanded — is restored by the library to "its most recent size",
  // which is a share of some earlier width; the preference is reapplied.
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
    // Expanded is a temporary shape, not the sizes to come back to.
    if (expanded) {
      return;
    }
    // The library reports shares; the preference is pixels, so the group's
    // own width turns one into the other. A pane at zero is collapsed, and a
    // collapse is recorded by its flag, not by a width of nothing.
    const width = (groupElementRef.current?.getBoundingClientRect().width ?? 0) - 2 * SEPARATOR_PX;
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

        <ResizablePanel
          id="session"
          panelRef={sessionRef}
          defaultSize={layout?.sessionWidth ?? PANE_LIMITS.session.default}
          minSize={PANE_LIMITS.session.min}
          collapsible
          collapsedSize={0}
          className="bg-background"
        >
          <SessionPane />
        </ResizablePanel>

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
      </ResizablePanelGroup>
    </div>
  );
}

/**
 * The three panes' shares of a group `width` px wide, from the two fixed
 * widths. Collapsed panes are zero; the session takes what the explorer
 * would have when the explorer is closed; the explorer is never squeezed
 * below its floor — the session gives way first, since the window has a
 * minimum that keeps the sidebar and the explorer's floor in reach.
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
 * command.
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
