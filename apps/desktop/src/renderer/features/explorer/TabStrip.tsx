import {
  ChevronDown,
  FileText,
  GitCompare,
  Globe,
  Maximize2,
  Minimize2,
  Plus,
  SquareTerminal,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { createElement, useEffect, useRef, useState } from "react";

import { Button } from "@renderer/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { cn } from "@renderer/lib/utils";
import { tabTitle, useExplorer } from "@renderer/state/explorer";
import type { ExplorerTab, ExplorerTabKind } from "@shared/types";

import { FileIcon } from "./icons";

/**
 * The one strip. Four kinds, no bottom panel (plan §3).
 *
 * `+` opens a file tab, which is what Codex's does; the chevron beside it is
 * where the other three kinds live, because a strip whose `+` opens a menu
 * costs a click on the common case to save one on the rare ones.
 *
 * Reordering is a plain HTML5 drag, not a library. What a tab strip needs is
 * "pick up a tab, drop it between two others"; `dragover` on a tab and an
 * index swap is the whole behaviour, and a drag-and-drop library here would be
 * 40 KB to do the same thing with more state.
 *
 * Far right: Codex has expand and split. Expand is implemented — the explorer
 * takes the window and the other two panes collapse. Split is not: two strips
 * would mean two selections, two persisted orders and a second answer to "what
 * does Cmd+1 mean", and the plan asks for one strip.
 */

const KIND_ICONS: Record<ExplorerTabKind, LucideIcon> = {
  file: FileText,
  review: GitCompare,
  browser: Globe,
  terminal: SquareTerminal,
};

const KIND_LABELS: Record<Exclude<ExplorerTabKind, "file">, string> = {
  review: "Review",
  browser: "Browser",
  terminal: "Terminal",
};

/**
 * A tab's icon: the file type for a file tab, the kind's glyph otherwise.
 *
 * A component rather than a `const Icon = …` in `TabButton`'s body, for the
 * reason spelt out in `icons.tsx` — picking an element type during render is
 * indistinguishable from defining one there.
 */
function TabIcon({ tab, className }: { tab: ExplorerTab; className?: string }) {
  if (tab.kind === "file" && tab.path) {
    return <FileIcon className={className} path={tab.path} />;
  }
  return createElement(KIND_ICONS[tab.kind], { className, strokeWidth: 1.75 });
}

/** The `+` menu's rows, so the dropdown does not select a type in render. */
function KindIcon({ kind, className }: { kind: ExplorerTabKind; className?: string }) {
  return createElement(KIND_ICONS[kind], { className });
}

export function TabStrip() {
  const tabs = useExplorer((state) => state.tabs);
  const activeId = useExplorer((state) => state.activeId);
  const open = useExplorer((state) => state.open);
  const close = useExplorer((state) => state.close);
  const setActive = useExplorer((state) => state.setActive);
  const move = useExplorer((state) => state.move);
  const expanded = useExplorer((state) => state.expanded);
  const toggleExpanded = useExplorer((state) => state.toggleExpanded);

  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  const stripRef = useRef<HTMLDivElement | null>(null);

  // A strip wider than the pane scrolls, and Cmd+5 selecting a tab that is
  // off the left edge would otherwise change the pane's contents with nothing
  // on screen to say which tab won.
  useEffect(() => {
    if (activeId) {
      stripRef.current
        ?.querySelector(`[data-tab="${CSS.escape(activeId)}"]`)
        ?.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [activeId, tabs.length]);

  return (
    <div
      className="app-drag flex shrink-0 items-center gap-1 border-b pr-1.5 pl-2"
      style={{ height: "var(--titlebar-height)" }}
    >
      <div
        className="app-no-drag flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto"
        ref={stripRef}
        role="tablist"
      >
        {tabs.map((tab, index) => (
          <TabButton
            active={tab.id === activeId}
            dragging={tab.id === draggingId}
            dropBefore={dropIndex === index && draggingId !== null && draggingId !== tab.id}
            key={tab.id}
            onClose={() => close(tab.id)}
            onDragEnd={() => {
              if (draggingId !== null && dropIndex !== null) {
                move(draggingId, dropIndex);
              }
              setDraggingId(null);
              setDropIndex(null);
            }}
            onDragOver={() => setDropIndex(index)}
            onDragStart={() => setDraggingId(tab.id)}
            onSelect={() => setActive(tab.id)}
            tab={tab}
          />
        ))}
      </div>

      {/*
        `+` is pinned rather than trailing the tabs. Codex puts it in the flow,
        which is fine in a full-width window and unusable in a 45% pane: with
        six tabs open the strip scrolls and the button that opens the seventh
        is the thing that scrolls off.
      */}
      <div className="app-no-drag flex shrink-0 items-center gap-0.5 border-l pl-1.5">
        <Button
          aria-label="New tab"
          className="size-6 rounded-r-none text-muted-foreground"
          onClick={() => open("file")}
          size="icon-xs"
          variant="ghost"
        >
          <Plus className="size-3.5" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              aria-label="New tab of another kind"
              className="h-6 w-4 rounded-l-none px-0 text-muted-foreground"
              size="icon-xs"
              variant="ghost"
            >
              <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            {(Object.keys(KIND_LABELS) as (keyof typeof KIND_LABELS)[]).map((kind) => (
              <DropdownMenuItem key={kind} onSelect={() => open(kind)}>
                <KindIcon className="size-3.5" kind={kind} />
                {KIND_LABELS[kind]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <Button
          aria-label={expanded ? "Restore layout" : "Expand explorer"}
          className="ml-0.5 size-6 text-muted-foreground"
          onClick={toggleExpanded}
          size="icon-xs"
          title={expanded ? "Restore layout" : "Expand explorer"}
          variant="ghost"
        >
          {expanded ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
        </Button>
      </div>
    </div>
  );
}

function TabButton({
  tab,
  active,
  dragging,
  dropBefore,
  onSelect,
  onClose,
  onDragStart,
  onDragOver,
  onDragEnd,
}: {
  tab: ExplorerTab;
  active: boolean;
  dragging: boolean;
  dropBefore: boolean;
  onSelect: () => void;
  onClose: () => void;
  onDragStart: () => void;
  onDragOver: () => void;
  onDragEnd: () => void;
}) {
  const title = tabTitle(tab);

  return (
    <div
      className={cn(
        "group/tab relative flex h-7 max-w-[190px] shrink-0 items-center gap-1.5 rounded-md pr-1 pl-2 text-[13px] transition-colors",
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
        dragging && "opacity-40",
        // The insertion point, drawn as a line rather than by shifting the
        // tabs: a strip whose tabs jump around under the cursor is hard to aim.
        dropBefore && "before:absolute before:inset-y-1 before:-left-0.5 before:w-0.5 before:rounded-full before:bg-primary",
      )}
      data-tab={tab.id}
      draggable
      onDragEnd={onDragEnd}
      onDragOver={(event) => {
        event.preventDefault();
        onDragOver();
      }}
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      // Middle-click closes, as it does in every tabbed thing.
      onPointerDown={(event) => {
        if (event.button === 1) {
          event.preventDefault();
          onClose();
        }
      }}
      role="tab"
      title={tab.kind === "file" && tab.path ? tab.path : title}
    >
      <button
        aria-selected={active}
        className="flex min-w-0 items-center gap-1.5 outline-none"
        onClick={onSelect}
        type="button"
      >
        <TabIcon className="size-3.5 shrink-0" tab={tab} />
        <span className="truncate">{title}</span>
      </button>
      <button
        aria-label={`Close ${title}`}
        className={cn(
          "flex size-4 shrink-0 items-center justify-center rounded-sm transition-opacity hover:bg-background/70",
          active ? "opacity-60 hover:opacity-100" : "opacity-0 group-hover/tab:opacity-100",
        )}
        onClick={onClose}
        type="button"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}
