import { FileText, GitCompare, Globe, Plus, SquareTerminal, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { createElement, useEffect, useRef, useState } from "react";

import { ExplorerToggle } from "@renderer/app/PaneToggles";
import { Button } from "@renderer/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { isMac } from "@renderer/lib/platform";
import { SHORTCUTS, shortcutKeys } from "@renderer/lib/shortcuts";
import { cn } from "@renderer/lib/utils";
import { tabTitle, useExplorer } from "@renderer/state/explorer";
import type { ExplorerTab, ExplorerTabKind } from "@shared/types";

import { FileIcon } from "./icons";

/**
 * The one strip. Four kinds, no bottom panel (plan §3).
 *
 * `+` opens the menu of the four kinds. It used to open a file tab, with a
 * chevron beside it for the other three, on the argument that a menu costs a
 * click on the common case — but two adjacent controls a quarter of an inch
 * wide, one of them a 4px chevron, cost aim on every case, and a person who
 * wants a file tab has the shortcut. One button, one menu, and the binding
 * printed on every row.
 *
 * `+` **trails the last tab and sticks to the right edge.** It scrolls with
 * the strip, so it reads as the end of the row rather than as a separate
 * control bolted to the corner — and `position: sticky` in the scrolling row
 * means that once the tabs overflow, it stops at the pane's right edge with
 * the tabs sliding underneath it instead of scrolling away with them. Pinning
 * it outside the scroller made it always visible but never part of the row;
 * leaving it in the flow made it part of the row and unreachable at six tabs
 * in a 45% pane. Sticky is both.
 *
 * Reordering is a plain HTML5 drag, not a library. What a tab strip needs is
 * "pick up a tab, drop it between two others"; `dragover` on a tab and an
 * index swap is the whole behaviour, and a drag-and-drop library here would be
 * 40 KB to do the same thing with more state.
 *
 * Neither of Codex's far-right controls is here. Fullscreen is gone: it was
 * the one thing in the app that could take the session pane away, and the
 * session is the app. Split was never built — two strips would mean two
 * selections, two persisted orders and a second answer to "what does Cmd+1
 * mean", and the plan asks for one strip.
 */

const KIND_ICONS: Record<ExplorerTabKind, LucideIcon> = {
  file: FileText,
  review: GitCompare,
  browser: Globe,
  terminal: SquareTerminal,
};

/** The menu's rows, in the order a person reaches for them. */
const KINDS: readonly { kind: ExplorerTabKind; label: string; shortcut: string }[] = [
  { kind: "file", label: "File", shortcut: "new-file-tab" },
  { kind: "review", label: "Review", shortcut: "new-review-tab" },
  { kind: "browser", label: "Browser", shortcut: "new-browser-tab" },
  { kind: "terminal", label: "Terminal", shortcut: "new-terminal-tab" },
];

/** The binding as the shortcut table has it — one declaration, two readers. */
function bindingOf(id: string): string {
  const shortcut = SHORTCUTS.find((candidate) => candidate.id === id);
  return shortcut ? shortcutKeys(shortcut.binding, isMac) : "";
}

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
  const collapsed = useExplorer((state) => state.collapsed);
  const activeId = useExplorer((state) => state.activeId);
  const open = useExplorer((state) => state.open);
  const close = useExplorer((state) => state.close);
  const setActive = useExplorer((state) => state.setActive);
  const move = useExplorer((state) => state.move);

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
      className="app-drag flex shrink-0 items-center border-b pr-3 pl-2"
      data-tab-strip
      style={{ height: "var(--titlebar-height)" }}
    >
      {/*
        `scroll-pr-10` is what keeps the selected tab out from under the
        pinned `+`: the scroll below aims for "nearest", and without the
        padding nearest is half a tab beneath it.
      */}
      <div
        className="no-scrollbar app-no-drag flex min-w-0 flex-1 scroll-pr-10 items-center overflow-x-auto"
        ref={stripRef}
      >
        {/* Only tabs are in the tablist; `+` is a control that follows it. */}
        <div className="flex shrink-0 items-center gap-0.5" role="tablist">
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
          The end of the row, and the right edge of the pane once the row is
          longer than the pane. `sticky right-0` is the whole mechanism; the
          background is what stops the tabs it is holding back from showing
          through, and the gradient to its left is what they fade into rather
          than being cut off against a hard edge.
        */}
        <div
          className="sticky right-0 z-10 flex shrink-0 items-center bg-background pr-0.5 pl-1 before:pointer-events-none before:absolute before:top-0 before:right-full before:h-full before:w-5 before:bg-gradient-to-r before:from-transparent before:to-background"
          data-new-tab
        >
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="New tab"
                className="size-6 text-muted-foreground"
                size="icon-xs"
                variant="ghost"
              >
                <Plus className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {KINDS.map(({ kind, label, shortcut }) => (
                <DropdownMenuItem key={kind} onSelect={() => open(kind)}>
                  <KindIcon className="size-3.5" kind={kind} />
                  {label}
                  <DropdownMenuShortcut>{bindingOf(shortcut)}</DropdownMenuShortcut>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      {/* The window's right edge while the explorer is open — outside the
          scrolling row, since `+` follows the last tab and only pins to the
          edge on overflow — the same spot the session's title bar holds this
          toggle in while the explorer is shut, so it never moves. A shut
          explorer keeps its strip in the document at zero width, so the
          title bar's is the only one then. */}
      {collapsed ? null : (
        <div className="app-no-drag flex shrink-0 items-center pl-1">
          <ExplorerToggle />
        </div>
      )}
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
        "group/tab relative flex h-[26px] max-w-[190px] shrink-0 items-center gap-1.5 rounded-md pr-0.5 pl-1.5 text-[13px] transition-colors",
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
