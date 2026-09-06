import { useEffect, useRef } from "react";
import type { Layout, LayoutChangedMeta, PanelImperativeHandle } from "react-resizable-panels";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@renderer/components/ui/resizable";
import { ExplorerPane } from "@renderer/features/explorer/ExplorerPane";
import { SessionPane } from "@renderer/features/session/SessionPane";
import { Sidebar } from "@renderer/features/sidebar/Sidebar";
import { useExplorer } from "@renderer/state/explorer";
import { useSettings } from "@renderer/state/settings";

/**
 * Three panes: projects, the session, the explorer (plan §3).
 *
 * Sizes are percentages persisted in settings, so the window comes back the
 * way it was left. The sidebar and the explorer collapse; the session never
 * does — it is the app.
 */
export function Shell() {
  const layout = useSettings((state) => state.settings?.layout);
  const setLayout = useSettings((state) => state.setLayout);
  const sidebarRef = useRef<PanelImperativeHandle | null>(null);
  const explorerRef = useRef<PanelImperativeHandle | null>(null);
  const sessionRef = useRef<PanelImperativeHandle | null>(null);

  // The explorer's expand affordance (the strip's far-right control, plan §2)
  // is a *view*, not a preference: it collapses the other two panes without
  // writing their collapsed flags, so leaving it restores what was there.
  const expanded = useExplorer((state) => state.expanded);

  const sidebarCollapsed = expanded || (layout?.sidebarCollapsed ?? false);
  const explorerCollapsed = !expanded && (layout?.explorerCollapsed ?? false);
  const sessionCollapsed = expanded;

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
    const total = (next.sidebar ?? 0) + (next.session ?? 0) + (next.explorer ?? 0);
    if (total <= 0) {
      return;
    }
    void setLayout({
      sidebar: percentage(next.sidebar, total),
      session: percentage(next.session, total),
      explorer: percentage(next.explorer, total),
    });
  };

  return (
    <div className="h-screen w-screen overflow-hidden bg-background text-foreground">
      <ResizablePanelGroup
        id="shell"
        orientation="horizontal"
        defaultLayout={
          layout
            ? { sidebar: layout.sidebar, session: layout.session, explorer: layout.explorer }
            : undefined
        }
        onLayoutChanged={onLayoutChanged}
      >
        <ResizablePanel
          id="sidebar"
          panelRef={sidebarRef}
          defaultSize="16%"
          minSize="160px"
          maxSize="34%"
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
          minSize="24%"
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
          defaultSize="45%"
          minSize="20%"
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

function percentage(value: number | undefined, total: number) {
  return Math.round(((value ?? 0) / total) * 1000) / 10;
}
