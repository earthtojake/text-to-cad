import { FileText, GitCompare, Globe, Plus, SquareTerminal, X } from "lucide-react";
import { cn } from "cn";

import { Button } from "@renderer/components/ui/button";
import { tabTitle, useExplorer } from "@renderer/state/explorer";
import type { ExplorerTab, ExplorerTabKind } from "@shared/types";

const KIND_ICONS: Record<ExplorerTabKind, React.ReactNode> = {
  file: <FileText className="size-3.5" />,
  review: <GitCompare className="size-3.5" />,
  browser: <Globe className="size-3.5" />,
  terminal: <SquareTerminal className="size-3.5" />,
};

/**
 * One tab strip, four kinds of tab, no bottom panel (plan §3). P3 gives each
 * kind a body; P4 makes the file tab render CAD through the viewer's
 * `CadFileView`.
 */
export function ExplorerPane() {
  const tabs = useExplorer((state) => state.tabs);
  const activeId = useExplorer((state) => state.activeId);
  const open = useExplorer((state) => state.open);
  const close = useExplorer((state) => state.close);
  const setActive = useExplorer((state) => state.setActive);

  const active = tabs.find((tab) => tab.id === activeId) ?? null;

  return (
    <div className="flex h-full flex-col border-l">
      <div
        className="app-drag flex shrink-0 items-stretch gap-1 overflow-x-auto px-2"
        style={{ height: "var(--titlebar-height)" }}
      >
        <div className="app-no-drag flex items-center gap-1">
          {tabs.map((tab) => (
            <TabButton
              active={tab.id === activeId}
              key={tab.id}
              onClose={() => close(tab.id)}
              onSelect={() => setActive(tab.id)}
              tab={tab}
            />
          ))}
          <Button
            aria-label="New tab"
            className="size-6 text-muted-foreground"
            onClick={() => open("file")}
            size="icon-xs"
            variant="ghost"
          >
            <Plus className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 border-t bg-card/40">
        {active ? <TabBody tab={active} /> : <EmptyExplorer onOpen={() => open("file")} />}
      </div>
    </div>
  );
}

function TabButton({
  tab,
  active,
  onSelect,
  onClose,
}: {
  tab: ExplorerTab;
  active: boolean;
  onSelect: () => void;
  onClose: () => void;
}) {
  return (
    <div
      className={cn(
        "group/tab flex h-7 max-w-[200px] items-center gap-1.5 rounded-md pr-1 pl-2 text-[13px] transition-colors",
        active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60",
      )}
    >
      <button className="flex min-w-0 items-center gap-1.5" onClick={onSelect} type="button">
        {KIND_ICONS[tab.kind]}
        <span className="truncate">{tabTitle(tab)}</span>
      </button>
      <button
        aria-label={`Close ${tabTitle(tab)}`}
        className="flex size-4 shrink-0 items-center justify-center rounded-sm opacity-0 transition-opacity group-hover/tab:opacity-100 hover:bg-background/60"
        onClick={onClose}
        type="button"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}

/**
 * Placeholder bodies. Each one names the phase that replaces it, so an empty
 * pane in a screenshot is legible instead of looking like a bug.
 */
function TabBody({ tab }: { tab: ExplorerTab }) {
  const copy: Record<ExplorerTabKind, string> = {
    file: "A file tree, Monaco, the markdown preview and the CAD file surface land in P3 and P4.",
    review: "Per-file diffs and Commit or push land in P3.",
    browser: "The webview and its chrome land in P3.",
    terminal: "xterm.js over node-pty lands in P3.",
  };
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
      <span className="text-muted-foreground">{KIND_ICONS[tab.kind]}</span>
      <p className="text-sm font-medium">{tabTitle(tab)}</p>
      <p className="max-w-[320px] text-xs text-muted-foreground">{copy[tab.kind]}</p>
    </div>
  );
}

function EmptyExplorer({ onOpen }: { onOpen: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
      <p className="text-sm font-medium">Nothing open</p>
      <p className="max-w-[300px] text-xs text-muted-foreground">
        Files, reviews, browsers and terminals all open here, in one strip.
      </p>
      <Button className="h-7 text-xs" onClick={onOpen} size="sm" variant="secondary">
        <Plus className="size-3.5" />
        Open a file
      </Button>
    </div>
  );
}
