import { PencilRuler, FileText, GitCompare, Globe, Plus, SquareTerminal, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { createElement, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

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

import { FileIcon } from "@text-to-cad/ui/navigation";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

import { EXPLORER_TABPANEL_ID, focusTabBody } from "./focus";
import { preloadTerminal } from "./load-terminal";

/**
 * The one strip. No bottom panel (plan §3).
 *
 * `+` opens the menu of tab kinds. It used to open a file tab, with a
 * chevron beside it for the other kinds, on the argument that a menu costs a
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
 * "pick up a tab, drop it between two others", and a drag-and-drop library
 * here would be 40 KB to do the same thing with more state. `dragover` on a
 * chip only moves the insertion line: before the chip on its left half, after
 * it (`dropAfter`) on its right half, so the last position is reachable. The
 * move happens on `onDrop`; `onDragEnd` fires for a dropped and a cancelled
 * drag alike and only puts the strip back, so a cancelled drag reorders
 * nothing.
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
  drawing: PencilRuler,
};

/** The menu's rows, in the order a person reaches for them. */
const KINDS: readonly { kind: ExplorerTabKind; label: string; shortcut: string }[] = [
  { kind: "file", label: "File", shortcut: "new-file-tab" },
  { kind: "review", label: "Review", shortcut: "new-review-tab" },
  { kind: "browser", label: "Browser", shortcut: "new-browser-tab" },
  { kind: "terminal", label: "Terminal", shortcut: "new-terminal-tab" },
  { kind: "drawing", label: "Drawing", shortcut: "new-drawing-tab" },
];

/** The binding as the shortcut table has it — one declaration, two readers. */
function bindingOf(id: string): string {
  const shortcut = SHORTCUTS.find((candidate) => candidate.id === id);
  return shortcut ? shortcutKeys(shortcut.binding, isMac) : "";
}

/**
 * The binding as the menu draws it. A backtick is a hairline beside the ⌘ ⇧ ⌃ glyphs and the
 * capital letters, easy to read as a stray mark or nothing at all, so it is drawn as a keycap of
 * the letters' height and read out by name.
 */
function ShortcutText({ keys }: { keys: string }) {
  const tick = keys.indexOf("`");
  if (tick === -1) return <>{keys}</>;
  return (
    <>
      {keys.slice(0, tick)}
      <kbd aria-hidden className="ml-0.5 inline-flex h-3.5 min-w-3.5 items-center justify-center rounded-[3px] border px-0.5 font-mono text-[11px] leading-none tracking-normal">`</kbd>
      <span className="sr-only">backtick</span>
      {keys.slice(tick + 1)}
    </>
  );
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

/**
 * The one body the strip controls. `ExplorerPane` renders it; the ids live here
 * (the panel's in `./focus`, which also looks for it) so the tab's `aria-controls`
 * and the panel's `aria-labelledby` are one pair.
 */
export { EXPLORER_TABPANEL_ID };
export const explorerTabDomId = (tabId: string) => `explorer-tab-${tabId}`;

/** The `+` menu's rows, so the dropdown does not select a type in render. */
function KindIcon({ kind, className }: { kind: ExplorerTabKind; className?: string }) {
  return createElement(KIND_ICONS[kind], { className });
}

export function TabStrip() {
  const ready = useExplorer((state) => state.ready);
  const tabs = useExplorer((state) => state.tabs);
  const activeId = useExplorer((state) => state.activeId);
  const open = useExplorer((state) => state.open);
  const close = useExplorer((state) => state.close);
  const setActive = useExplorer((state) => state.setActive);
  const move = useExplorer((state) => state.move);

  const [draggingId, setDraggingId] = useState<string | null>(null);
  // Roving tabindex: the strip is one Tab stop. Arrows move focus between tabs
  // without selecting (manual activation — a selected terminal or browser tab
  // mounts a pty or a webview, too costly to do per keypress); Enter or Space
  // selects. While focus is outside the strip, its stop is the selected tab.
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const stopId =
    (focusedId && tabs.some((tab) => tab.id === focusedId) ? focusedId : null) ??
    (activeId && tabs.some((tab) => tab.id === activeId) ? activeId : null) ??
    tabs[0]?.id ??
    null;
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  const stripRef = useRef<HTMLDivElement | null>(null);
  const newTabRef = useRef<HTMLButtonElement | null>(null);
  // Whether the row is longer than the pane. Only then does `+` hold tabs
  // back, and only then is the fade to its left drawn — over a row that
  // fits, the fade would dim the last tab's edge for nothing.
  const [overflowing, setOverflowing] = useState(false);
  useEffect(() => {
    const element = stripRef.current;
    if (!element) {
      return;
    }
    const measure = () => setOverflowing(element.scrollWidth > element.clientWidth + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [tabs.length]);

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

  const focusTab = (id: string | undefined) => {
    if (!id) return;
    setFocusedId(id);
    stripRef.current?.querySelector<HTMLElement>(`[data-tab="${CSS.escape(id)}"]`)?.focus();
  };

  // However a tab closes — its close button, Cmd+W, Delete — a close that took the focused
  // element with it (the button, or Monaco or a terminal in its body) leaves focus on the page,
  // where no key reaches the strip. It goes to the tab selected next, or to `+` when none is left.
  // Focus that is anywhere else — the composer — is not taken, and neither is the page's own:
  // only while the person was last in the strip or the tab's body. A click on transcript text
  // also leaves focus on the page, and a session switch or an agent's close_tab after it must
  // not pull focus across the window.
  const inside = useRef(false);
  // Whether the last thing the person did was a key rather than a pointer: a close by Cmd+W hands
  // focus over by script, and Chromium draws no focus-visible ring for that when what had focus
  // (Monaco, a terminal) was reached with the mouse — the new tab has focus and nothing shows it.
  const keyed = useRef(false);
  useEffect(() => {
    const note = (event: Event) => {
      if (event.type === "pointerdown") keyed.current = false;
      const target = event.target instanceof Node ? event.target : null;
      // A menu is portaled out of the strip; the strip's own menus close tabs too.
      if (!target || (target instanceof Element && target.closest("[role=menu]"))) return;
      inside.current = Boolean(stripRef.current?.contains(target) || document.getElementById(EXPLORER_TABPANEL_ID)?.contains(target));
    };
    const key = () => {
      keyed.current = true;
    };
    document.addEventListener("focusin", note, true);
    document.addEventListener("pointerdown", note, true);
    document.addEventListener("keydown", key, true);
    return () => {
      document.removeEventListener("focusin", note, true);
      document.removeEventListener("pointerdown", note, true);
      document.removeEventListener("keydown", key, true);
    };
  }, []);
  const shownIds = useRef(tabs.map((tab) => tab.id));
  useEffect(() => {
    const ids = tabs.map((tab) => tab.id);
    const closed = shownIds.current.some((id) => !ids.includes(id));
    shownIds.current = ids;
    if (!closed || !inside.current || (document.activeElement && document.activeElement !== document.body)) return;
    // The tab's own onFocus records it as the strip's Tab stop.
    const next =
      activeId && ids.includes(activeId) ? stripRef.current?.querySelector<HTMLElement>(`[data-tab="${CSS.escape(activeId)}"]`) : newTabRef.current;
    if (!next) return;
    next.focus();
    // After a key, the ring focus-visible would have drawn, drawn by the strip until focus leaves.
    if (keyed.current) {
      next.setAttribute("data-focus-handed", "");
      next.addEventListener("blur", () => next.removeAttribute("data-focus-handed"), { once: true });
    }
  }, [tabs, activeId]);

  const onTabKeyDown = (event: ReactKeyboardEvent<HTMLElement>, index: number) => {
    // Only the tab itself: a key pressed on its close button is that button's.
    if (event.target !== event.currentTarget) return;
    const tab = tabs[index];
    if (!tab) return;
    const last = tabs.length - 1;
    const target =
      event.key === "ArrowRight" ? tabs[index === last ? 0 : index + 1]
        : event.key === "ArrowLeft" ? tabs[index === 0 ? last : index - 1]
          : event.key === "Home" ? tabs[0]
            : event.key === "End" ? tabs[last]
              : null;
    if (target) {
      event.preventDefault();
      focusTab(target.id);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setActive(tab.id);
      return;
    }
    // Backspace too: the key macOS labels "delete" sends it.
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      const neighbour = tabs[index + 1] ?? tabs[index - 1];
      close(tab.id);
      // A close can be refused (unsaved changes); focus moves only if it went. The last tab has
      // no neighbour: focus goes to `+`, the strip's one control left, rather than to the page.
      window.requestAnimationFrame(() => {
        if (!useExplorer.getState().tabs.some((candidate) => candidate.id === tab.id)) {
          if (neighbour) focusTab(neighbour.id);
          else newTabRef.current?.focus();
        }
      });
    }
  };

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
        className="no-scrollbar app-drag flex min-w-0 flex-1 scroll-pr-10 items-center overflow-x-auto"
        ref={stripRef}
      >
        {/* Only tabs are in the tablist; `+` is a control that follows it. */}
        <div
          aria-label="Explorer tabs"
          aria-orientation="horizontal"
          className="app-no-drag flex shrink-0 items-center gap-0.5"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocusedId(null);
          }}
          // Out of the strip the line goes: a drag that ends elsewhere has nowhere it would land.
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropIndex(null);
          }}
          role="tablist"
        >
          {tabs.map((tab, index) => (
            <TabButton
              active={tab.id === activeId}
              focusable={tab.id === stopId}
              dragging={tab.id === draggingId}
              dropBefore={dropIndex === index && draggingId !== null && draggingId !== tab.id}
              // Past the last chip: the one place no tab is "the one it is before".
              dropAfter={dropIndex === tabs.length && index === tabs.length - 1 && draggingId !== null && draggingId !== tab.id}
              key={tab.id}
              onClose={() => close(tab.id)}
              // The end of every drag, dropped or cancelled (Escape, a release outside the
              // strip): it only puts the strip back. The reorder is `onDrop`'s.
              onDragEnd={() => {
                setDraggingId(null);
                setDropIndex(null);
              }}
              onDrop={() => {
                const from = tabs.findIndex((candidate) => candidate.id === draggingId);
                if (draggingId !== null && dropIndex !== null && from >= 0) {
                  // The line is drawn before the tab at `dropIndex` (`tabs.length` is after the
                  // last); `move` lands in the strip without the tab it lifts, which is one
                  // place earlier for a drag forward.
                  move(draggingId, from < dropIndex ? dropIndex - 1 : dropIndex);
                }
                setDraggingId(null);
                setDropIndex(null);
              }}
              // The right half of a chip is "after it": without that the strip has no end to drop on.
              onDragOver={(after) => setDropIndex(after ? index + 1 : index)}
              onDragStart={() => setDraggingId(tab.id)}
              onFocus={() => setFocusedId(tab.id)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
              onSelect={() => {
                setActive(tab.id);
                // A click is the person picking the tab: its body may take the keyboard.
                // Enter and Space leave focus on the tab, as a tab list's keys do.
                focusTabBody(tab.id);
              }}
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
          className={cn(
            "app-no-drag sticky right-0 z-10 flex shrink-0 items-center bg-background pr-0.5 pl-1",
            overflowing &&
              "before:pointer-events-none before:absolute before:top-0 before:right-full before:h-full before:w-5 before:bg-gradient-to-r before:from-transparent before:to-background",
          )}
          data-overflowing={overflowing ? "true" : undefined}
          data-new-tab
        >
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="New tab"
                disabled={!ready}
                ref={newTabRef}
                className="size-6 text-muted-foreground data-[focus-handed]:ring-[3px] data-[focus-handed]:ring-ring/50"
                size="icon-xs"
                variant="ghost"
              >
                <Plus className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {KINDS.map(({ kind, label, shortcut }) => (
                <DropdownMenuItem key={kind} onSelect={() => {
                  if (kind === "terminal") preloadTerminal();
                  const opened = open(kind);
                  if (opened) focusTabBody(opened.id);
                }}>
                  <KindIcon className="size-3.5" kind={kind} />
                  {label}
                  <DropdownMenuShortcut><ShortcutText keys={bindingOf(shortcut)} /></DropdownMenuShortcut>
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
          explorer is not rendered at all (`Shell`), so this strip existing is
          the same fact as the pane being open: there is never a second copy
          of this button hidden in a pane nobody can see. */}
      <div className="app-no-drag flex shrink-0 items-center pl-1">
        <ExplorerToggle />
      </div>
    </div>
  );
}

/**
 * One tab. The chip is the drag handle; the `tab` in it is the focus stop and
 * the selection, and the close button beside it is reachable by pointer and by
 * `Delete`, never by Tab: a strip of eight tabs is one Tab stop, not sixteen.
 */
function TabButton({
  tab,
  active,
  focusable,
  dragging,
  dropBefore,
  dropAfter,
  onSelect,
  onClose,
  onFocus,
  onKeyDown,
  onDragStart,
  onDragOver,
  onDragEnd,
  onDrop,
}: {
  tab: ExplorerTab;
  active: boolean;
  focusable: boolean;
  dragging: boolean;
  dropBefore: boolean;
  dropAfter: boolean;
  onSelect: () => void;
  onClose: () => void;
  onFocus: () => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
  onDragStart: () => void;
  onDragOver: (after: boolean) => void;
  onDragEnd: () => void;
  onDrop: () => void;
}) {
  const title = tabTitle(tab);

  return (
    // The chip: drawn, dragged and middle-clicked as one. It is not the tab — a tab holds no
    // other control (nested-interactive) — so the tab and its close button are siblings in it.
    <div
      className={cn(
        "group/tab relative flex h-7 max-w-[190px] shrink-0 cursor-default items-center rounded-lg border pr-1 text-[13px] transition-colors",
        // Inset: the strip scrolls (overflow-x-auto), which clips anything drawn outside
        // the chip, and an offset ring came through as four bracket fragments.
        "has-[[role=tab]:focus-visible]:ring-2 has-[[role=tab]:focus-visible]:ring-ring has-[[role=tab]:focus-visible]:ring-inset",
        "has-[[data-focus-handed]]:ring-2 has-[[data-focus-handed]]:ring-ring has-[[data-focus-handed]]:ring-inset",
        active
          ? "border-border bg-accent/80 font-medium text-accent-foreground shadow-xs"
          : "border-transparent text-muted-foreground hover:bg-accent/50 hover:text-foreground",
        dragging && "opacity-40",
        // The insertion point, drawn as a line rather than by shifting the
        // tabs: a strip whose tabs jump around under the cursor is hard to aim.
        dropBefore && "before:absolute before:inset-y-1 before:-left-0.5 before:w-0.5 before:rounded-full before:bg-primary",
        dropAfter && "after:absolute after:inset-y-1 after:-right-0.5 after:w-0.5 after:rounded-full after:bg-primary",
      )}
      draggable
      onClick={onSelect}
      onDragEnd={onDragEnd}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        const box = event.currentTarget.getBoundingClientRect();
        onDragOver(event.clientX >= box.left + box.width / 2);
      }}
      onDrop={(event) => {
        event.preventDefault();
        onDrop();
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
      role="none"
    >
      {/* A file's path is always the hint; any other tab's title only when the chip clips it. */}
      <TooltipHint content={tab.kind === "file" && tab.path ? tab.path : title} overflowOnly={!(tab.kind === "file" && tab.path)}>
        <div
          // Only the selected tab names the panel: the one body shows its content.
          aria-controls={active ? EXPLORER_TABPANEL_ID : undefined}
          // The keyboard's close, since the button beside it is the pointer's.
          aria-keyshortcuts="Delete"
          aria-selected={active}
          className="peer flex h-full min-w-0 flex-1 items-center gap-1.5 pl-2 outline-none"
          data-tab={tab.id}
          // The path a file tab shows, for the e2e suite: the hint above carries it for people.
          data-tab-path={tab.kind === "file" && tab.path ? tab.path : undefined}
          id={explorerTabDomId(tab.id)}
          onFocus={(event) => {
            if (event.target === event.currentTarget) onFocus();
          }}
          onKeyDown={onKeyDown}
          role="tab"
          tabIndex={focusable ? 0 : -1}
        >
          <TabIcon className="size-3.5 shrink-0" tab={tab} />
          <span className="truncate">{title}</span>
        </div>
      </TooltipHint>
      {/* Out of the Tab order and out of the accessibility tree: Delete on the tab is its
          keyboard twin, and a button a screen reader could reach would be a second stop per tab. */}
      <button
        aria-hidden
        aria-label={`Close ${title}`}
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded-md outline-none transition-opacity hover:bg-background/70",
          active ? "opacity-60 hover:opacity-100" : "opacity-0 group-hover/tab:opacity-100 peer-focus-visible:opacity-100",
        )}
        onClick={(event) => {
          // Closing is not also a click on the tab behind it.
          event.stopPropagation();
          onClose();
        }}
        tabIndex={-1}
        type="button"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}
