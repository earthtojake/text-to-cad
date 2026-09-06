import { FolderOpen, PanelsTopLeft, Plus } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@renderer/components/ui/button";
import { isMac } from "@renderer/lib/platform";
import { useActiveProject } from "@renderer/state/projects";
import { useActiveTab, useExplorer } from "@renderer/state/explorer";
import type { ExplorerTab } from "@shared/types";
import type { Project } from "@shared/types";

import { BrowserTab } from "./BrowserTab";
import { EmptyState } from "./EmptyState";
import { FileTab } from "./FileTab";
import { ReviewTab } from "./ReviewTab";
import { TabStrip } from "./TabStrip";
import { TerminalTab } from "./TerminalTab";

/**
 * The explorer: one tab strip and whatever the selected tab renders.
 *
 * Every tab kind is kept mounted only while it is selected. That is the
 * cheaper half of a real trade-off — a webview and an xterm each cost a
 * process and a canvas, and eight background tabs of them is a slow window —
 * and the state that would otherwise be lost is kept where it belongs instead:
 * the pty's output in main, the browser's URL on the tab, the file's draft in
 * the tab's own component, the tree's geometry in the store.
 */
export function ExplorerPane() {
  const project = useActiveProject();
  const tabs = useExplorer((state) => state.tabs);
  const ready = useExplorer((state) => state.ready);
  const open = useExplorer((state) => state.open);
  const active = useActiveTab();

  useExplorerShortcuts();

  if (!project) {
    return (
      <Frame>
        <EmptyState
          description="Files, reviews, browsers and terminals open here, in one strip — once there is a project to open them from."
          icon={FolderOpen}
          title="No project"
        />
      </Frame>
    );
  }

  return (
    <Frame>
      <TabStrip />
      <div className="min-h-0 flex-1">
        {active ? (
          <TabBody key={active.id} project={project} tab={active} />
        ) : (
          <EmptyState
            action={
              <Button className="h-7 gap-1.5 text-xs" onClick={() => open("file")} size="sm" variant="secondary">
                <Plus className="size-3.5" />
                Open a file
              </Button>
            }
            description={
              ready && tabs.length === 0
                ? "Files, reviews, browsers and terminals all open here, in one strip."
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

function TabBody({ tab, project }: { tab: ExplorerTab; project: Project }) {
  switch (tab.kind) {
    case "file":
      return (
        <FileTab
          path={tab.path}
          project={project}
          tabId={tab.id}
          viewSource={tab.viewSource}
        />
      );
    case "review":
      return <ReviewTab project={project} scope={tab.scope} tabId={tab.id} />;
    case "browser":
      return <BrowserTab tabId={tab.id} url={tab.url} />;
    case "terminal":
      return (
        <TerminalTab
          cwd={tab.cwd}
          project={project}
          ptyId={tab.ptyId}
          readOnly={tab.readOnly}
          tabId={tab.id}
        />
      );
  }
}

/**
 * The strip's keyboard.
 *
 * On the window rather than on the strip, because the chords have to work
 * while the focus is inside a tab's body — an editor, a terminal, a webview —
 * which is where it usually is. `Cmd/Ctrl+W` is intercepted before the menu's
 * default close-window accelerator: with tabs open it means "close this tab",
 * and only an empty strip lets it close the window.
 */
function useExplorerShortcuts() {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const modifier = isMac ? event.metaKey : event.ctrlKey;
      if (!modifier || event.altKey) {
        return;
      }
      const { tabs, activeId, closeActive, selectIndex } = useExplorer.getState();

      if (event.key.toLowerCase() === "w" && !event.shiftKey && activeId) {
        event.preventDefault();
        closeActive();
        return;
      }
      if (/^[1-9]$/.test(event.key) && tabs.length > 0) {
        event.preventDefault();
        // 9 is the last tab, the way browsers do it — otherwise the ninth
        // shortcut is dead in every strip with fewer than nine tabs.
        selectIndex(event.key === "9" ? tabs.length : Number(event.key));
      }
    };
    // Capture: a terminal and Monaco both swallow keys on the bubble phase.
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);
}
