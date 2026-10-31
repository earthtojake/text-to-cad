import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Clapperboard, FileText, ListTree, Menu, X } from "lucide-react";
import { ChangedDot, PositionIcon } from "./ChangedDot.jsx";
import { ToggleGroup, ToggleGroupItem } from "@text-to-cad/ui/primitives/toggle-group";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { cn } from "@text-to-cad/ui/utils";
import { FILE_SIDEBAR_SURFACE_CLASS, FLOATING_CHROME_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { STRIP_BUTTON_CLASS, TOUCH_STRIP_BUTTON_CLASS } from "./stripTouch.js";
import { capturePointer, releasePointer } from "../../../lib/pointerCapture.js";
import ResizeGrip from "./ResizeGrip.jsx";
import { ToolStackContext } from "./ToolStack.jsx";
import { useControlUsage } from "../../../usage/controls.js";
import { useI18n } from "@text-to-cad/ui/i18n";
import { FILE_SIDEBAR_MIN_WIDTH, TOOL_PANEL_WIDTH, fileSidebarSizeId, clampToolPanelHeight, clampToolPanelWidth, normalizeToolStack } from "./toolStackLayout.js";

const KEY_NUDGE_PX = 16;
// A phone's panel: a joint's name and its slider side by side, within the view's inset.
const PHONE_PANEL_WIDTH = 288;

// How the sidebar's panel slides in and out from its edge (and Preview's settings from theirs):
// its translate and opacity, 200ms, easing out; at once where motion is reduced.
export const SIDEBAR_SLIDE_CLASS = "transition-[translate,opacity] duration-200 ease-out motion-reduce:transition-none";

/**
 * The file's sidebar: what there is to read of the file, its hierarchy, properties and controls,
 * whatever tool is in hand. The toolbar is for using tools; this is for the file. It is a toolbar
 * of its own at the viewer's top-left, one tile per section (`ToolPanel`s drawn as sections,
 * `ToolStackContext`'s `sidebar`): a tree by its name (**Model tree**, **Links**: a tree icon, its
 * filter heading the panel), **Position**
 * for a model's joints, **Animation** for its routines (**Motion** for an engine document's
 * motions), and any other section by its name. None is open as a file opens; a tile
 * opens its section in a panel under the toolbar, a second press on it closes it, and so does the
 * section's own collapse button; another tile opens its section instead. One section at a time.
 * The panel is read for as long as it is open, so it has its own surface (`FILE_SIDEBAR_SURFACE_CLASS`):
 * lighter than a menu's, heavier than the strip's. Every section stays mounted, closed or not, so
 * a tree keeps its expansion, filter and scroll.
 *
 * The open section is its content's height, up to the panel's cap — the room under the toolbar
 * within the viewer's inset, unless the person has set one — and past that it scrolls. A tree's
 * rows are mounted as the panel's scroll brings them into view (`VirtualRows.jsx`); the section's
 * head — its heading and, for a tree, its filter — pins to the top.
 *
 * Its size is the person's, from its bottom-right corner (Quick Edit's grip, as a resizable panel
 * has): width and cap together, by pointer, or by keyboard (arrows by 16px; Home and End to the
 * bounds), written back once a gesture lets go — each section's own (`layout.panels["sidebar:<id>"]`). It opens a tool panel's
 * width, and may be made narrower than that (`FILE_SIDEBAR_MIN_WIDTH`).
 *
 * On a phone (`phone`) the toolbar is one touch-sized tile, the sidebar's (a menu icon), which
 * opens the panel on the section last open (the first, at first) and closes it; the panel's top is
 * a row of tabs, one per section with its tile's icon, and it runs down the view to its bottom
 * inset (clear of Quick Edit's peek), or as tall as the section if that is less, at a phone's own
 * width — wide enough for a joint's name beside its slider, not a wide view's size — with no grip.
 *
 * It is the tools view's alone: Preview hides it (`hidden`), its sections kept mounted.
 *
 * @param {{ layout: { panels: object, collapsed: object },
 *   onLayoutChange(patch: object | ((layout: object) => object)): void, hidden?: boolean,
 *   phone?: boolean,
 *   style?: import("react").CSSProperties, children?: import("react").ReactNode }} props
 *   `style` places the room the toolbar and its panel may take; they hang from its top-left corner.
 */
export default function FileSidebar({ layout: stored, onLayoutChange, hidden = false,
  phone = false, style, children }) {
  const { t } = useI18n();
  const layout = useMemo(() => normalizeToolStack(stored), [stored]);
  const room = useRef(null), bar = useRef(null), scroller = useRef(null), column = useRef(null);
  // The room's height, the most the bar may take, and the viewer's width, which bounds the bar's.
  const [measured, setMeasured] = useState({ room: 0, viewer: 0 });
  useLayoutEffect(() => {
    const element = room.current;
    if (!element) return undefined;
    const viewer = element.closest("[data-cad-scene-backdrop]");
    const measure = () => setMeasured(current => {
      const next = { room: element.clientHeight, viewer: Math.round(viewer?.getBoundingClientRect().width || 0) };
      return current.room === next.room && current.viewer === next.viewer ? current : next;
    });
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (viewer) observer.observe(viewer);
    return () => observer.disconnect();
  }, []);
  const clampWidth = value => clampToolPanelWidth(value, measured.viewer || window.innerWidth, FILE_SIDEBAR_MIN_WIDTH);
  const clampHeight = value => clampToolPanelHeight(value, measured.room || Infinity);
  const [draft, setDraft] = useState(null);

  const settle = useCallback((id, change) => onLayoutChange(current => {
    const patch = {};
    if (change.width !== undefined || change.height !== undefined) {
      const next = { ...current.panels[id] };
      if (change.width !== undefined) next.width = change.width;
      if (change.height !== undefined) next.height = change.height;
      patch.panels = { ...current.panels, [id]: next };
    }
    if (change.collapsed !== undefined) {
      const next = { ...current.collapsed };
      if (change.collapsed === Boolean(change.fallback)) delete next[id]; else next[id] = change.collapsed;
      patch.collapsed = next;
    }
    return patch;
  }), [onLayoutChange]);
  // Each section's head (`ToolPanel.jsx`'s, its heading and header) at its anchor, just before it.
  // Below the view, a head docks at the bottom over the heads after it: each sticks that far up
  // (`data-stuck`, drawn above its anchor). The head of the section the view is in pins to the
  // top (`data-pinned`, its anchor above the view), until the next head arrives and pushes it off.
  // The pinned and docked heads pad the scroller, so what is scrolled into view clears them.
  const dock = useCallback(() => {
    const element = scroller.current;
    const heads = [...(column.current?.querySelectorAll(":scope > section:not([hidden]):not([data-sidebar-closed]) > [data-sidebar-head]") ?? [])];
    if (!element || !heads.length) return;
    const viewTop = element.getBoundingClientRect().top;
    const anchorTop = head => head.previousElementSibling?.getBoundingClientRect().top ?? 0;
    // The section the view is in: the last whose anchor has reached the top.
    const current = heads.findLastIndex(head => anchorTop(head) <= viewTop + 0.5);
    let below = 0, docked = 0, pinned = 0;
    for (let index = heads.length - 1; index >= 0; index -= 1) {
      const head = heads[index];
      head.style.bottom = `${below}px`;
      below += head.offsetHeight;
      head.style.top = index === current ? "0px" : "auto";
      const push = index === current && heads[index + 1] ? Math.min(0, anchorTop(heads[index + 1]) - viewTop - head.offsetHeight) : 0;
      head.style.translate = push ? `0 ${push}px` : "";
      head.toggleAttribute("data-pinned", index === current && anchorTop(head) < viewTop - 0.5);
      if (index === current) pinned = Math.max(0, head.offsetHeight + push);
      const stuck = anchorTop(head) > head.getBoundingClientRect().top + 0.5;
      head.toggleAttribute("data-stuck", stuck);
      if (stuck) docked += head.offsetHeight;
    }
    element.style.scrollPaddingTop = `${pinned}px`;
    element.style.scrollPaddingBottom = `${docked}px`;
  }, []);
  useLayoutEffect(dock);
  // Which sections are on screen, in order: the first carries the bar's own button.
  const [order, setOrder] = useState("");
  useLayoutEffect(() => {
    const ids = [...(column.current?.querySelectorAll(":scope > section:not([hidden])") ?? [])]
      .map(section => section.getAttribute("data-tool-panel-id") || "").join(" ");
    if (ids !== order) setOrder(ids);
  });
  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element) return undefined;
    element.addEventListener("scroll", dock, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(dock);
    observer?.observe(element);
    if (column.current) observer?.observe(column.current);
    return () => { element.removeEventListener("scroll", dock); observer?.disconnect(); };
  }, [dock]);
  const ids = order ? order.split(" ") : [];
  // The open section: none as a file opens, and none once the one open is gone.
  const [openId, setOpenId] = useState(null);
  const open = openId !== null && ids.includes(openId) ? openId : null;
  // The section the panel shows: the open one, and while the panel slides away, the one it held.
  const lastOpen = useRef(null);
  if (open) lastOpen.current = open;
  const shown = open ?? (ids.includes(lastOpen.current) ? lastOpen.current : null);
  // Each section's panel has a size of its own, the person's, kept under its id.
  const sizeId = fileSidebarSizeId(shown);
  const size = { ...layout.panels[sizeId], ...draft };
  const width = phone ? Math.min(PHONE_PANEL_WIDTH, (measured.viewer || window.innerWidth) - 16) : clampWidth(size.width ?? TOOL_PANEL_WIDTH);
  const cap = size.height !== undefined ? clampHeight(size.height) : measured.room || null;
  // The section's X closes it and puts its size back to the default (the tile pressed again only
  // closes it, the less destructive way out: its size is kept for the next time).
  const shownRef = useRef(shown);
  shownRef.current = shown;
  const layoutRef = useRef(layout);
  layoutRef.current = layout;
  const closeSection = useCallback(() => {
    const id = fileSidebarSizeId(shownRef.current);
    setOpenId(null);
    setDraft(null);
    // A size never set is nothing to put back: nothing is stored until a person sizes it.
    if (!layoutRef.current.panels?.[id]) return;
    onLayoutChange(current => {
      if (!current.panels?.[id]) return {};
      const { [id]: _dropped, ...panels } = current.panels;
      return { panels };
    });
  }, [onLayoutChange]);
  // What each section's tile says, as the section reports it (`register`, from `ToolPanel.jsx`).
  const meta = useRef(new Map());
  const [metaTick, setMetaTick] = useState(0);
  const register = useCallback((id, next) => {
    const current = meta.current.get(id);
    if (current && current.title === next.title && current.fit === next.fit && Boolean(current.changed) === Boolean(next.changed)) return;
    meta.current.set(id, next);
    setMetaTick(tick => tick + 1);
  }, []);
  // A phone's panel with more than one section is headed by their tabs and its one X.
  const tabbed = phone && ids.length > 1;
  const sections = useMemo(() => ({
    sidebar: true,
    openSection: shown,
    closeSection,
    // Whether a section's head carries its X: not under a phone's tabs, whose row has the panel's.
    closeInHead: !tabbed,
    register,
    viewerWidth: measured.viewer,
    size: () => null,
    defaultHeight: () => null,
    collapsed: (id, fallback) => layout.collapsed[id] ?? fallback,
    settle,
    room: () => room.current?.clientHeight || 0,
  }), [shown, closeSection, tabbed, register, measured.viewer, layout, settle]);
  const tiles = ids.map(id => {
    const section = meta.current.get(id) || {};
    const tile = section.fit === "tree" ? { label: section.title || t("sidebar.tree"), Icon: ListTree }
      : id === "position" ? { label: t("sidebar.position"), Icon: PositionIcon }
        : id === "animation" ? { label: section.title || t("sidebar.animation"), Icon: Clapperboard }
        : { label: section.title || id, Icon: FileText };
    return { id, ...tile, changed: Boolean(section.changed) };
  });
  void metaTick;
  // A press of a tile: its section opens, or closes if it was the open one.
  const toggle = useCallback(id => setOpenId(current => (current === id ? null : id)), []);
  // A section a person opens, by its id (`usage/controls.js`: `sidebar_tree`).
  const controls = useControlUsage();
  // A phone's one tile: the panel opens on the section last open, or the first, and closes.
  const togglePanel = () => setOpenId(current => (current && ids.includes(current) ? null : ids.includes(lastOpen.current) ? lastOpen.current : tiles[0]?.id ?? null));

  // The corner moves both: the width and the cap, from the size on screen.
  const drag = useRef(null);
  const drawn = () => {
    const box = bar.current?.getBoundingClientRect();
    return { width: box?.width || width, height: box?.height || cap || 0 };
  };
  const startDrag = event => {
    if (event.button !== 0) return;
    event.preventDefault();
    drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, from: drawn(), next: null };
    capturePointer(event.currentTarget, event.pointerId);
  };
  const moveDrag = event => {
    const current = drag.current;
    if (current?.pointerId !== event.pointerId) return;
    current.next = { width: clampWidth(current.from.width + event.clientX - current.x), height: clampHeight(current.from.height + event.clientY - current.y) };
    setDraft(current.next);
  };
  const stopDrag = event => {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    drag.current = null;
    releasePointer(event.currentTarget, event.pointerId);
    setDraft(null);
    if (current.next) settle(sizeId, current.next);
  };
  const keyDrag = event => {
    const from = drawn(), change = {};
    const nextWidth = { ArrowLeft: from.width - KEY_NUDGE_PX, ArrowRight: from.width + KEY_NUDGE_PX, Home: 0, End: Infinity }[event.key];
    const nextHeight = { ArrowUp: from.height - KEY_NUDGE_PX, ArrowDown: from.height + KEY_NUDGE_PX, Home: 0, End: Infinity }[event.key];
    if (nextWidth !== undefined) change.width = clampWidth(nextWidth);
    if (nextHeight !== undefined) change.height = clampHeight(nextHeight);
    if (!Object.keys(change).length) return;
    event.preventDefault();
    settle(sizeId, change);
  };

  const aside = <aside ref={bar} aria-label={t("sidebar.file")} data-cad-file-sidebar="" data-open={open ? "" : undefined} inert={!open}
    className={cn("relative flex max-w-full flex-col overflow-hidden text-tiny", SIDEBAR_SLIDE_CLASS,
      "rounded-md", FILE_SIDEBAR_SURFACE_CLASS,
      open ? "pointer-events-auto" : "pointer-events-none -translate-x-[calc(100%+1rem)] opacity-0")}
    // Never wider than the room left of the tool strip (`--cad-file-sidebar-max-width`, the shell's
    // measure): it stops an inset short of the strip and its row rather than reaching under them.
    style={{ width, maxHeight: cap ?? undefined, maxWidth: phone ? undefined : `max(${FILE_SIDEBAR_MIN_WIDTH}px, var(--cad-file-sidebar-max-width, 100%))` }}>
    {/* A phone's panel is headed by its sections' tabs, each with its tile's icon, and the panel's
        one X at the row's right end (its sections' heads then have none). */}
    {tabbed ? <div className="flex shrink-0 items-center gap-1 border-b border-border/60 p-1" data-file-sidebar-tabs="">
      <ToggleGroup type="single" value={shown ?? ""} onValueChange={id => { if (id) { controls.used(`sidebar_${id}`); setOpenId(id); } }} aria-label={t("sidebar.sections")} className="min-w-0 flex-1">
        {tiles.map(({ id, label, Icon, changed }) => <ToggleGroupItem key={id} value={id} aria-label={label} className="h-9" data-file-sidebar-tab={id}>
          {/* The dot at the icon's corner, not the wide tab's. */}
          <span className="relative inline-flex"><Icon className="size-4.5" aria-hidden="true" />
            {changed ? <ChangedDot className="-right-1 -top-0.5" /> : null}</span>
        </ToggleGroupItem>)}
      </ToggleGroup>
      <button type="button" aria-label={t("sidebar.close")} onClick={closeSection} data-file-sidebar-close=""
        className="flex size-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45">
        <X className="size-4" aria-hidden="true" />
      </button>
    </div> : null}
    <ScrollArea className="min-h-0 flex-1" viewportRef={scroller} viewportProps={{ "data-file-sidebar-scroller": "" }}>
      {/* The section's head needs no rule above it: the panel's edge is there. */}
      <div ref={column} className="flex flex-col [&>section>[data-sidebar-head]]:border-t-0">
        <ToolStackContext.Provider value={sections}>{children}</ToolStackContext.Provider>
      </div>
    </ScrollArea>
    {phone ? null : <ResizeGrip corner="bottom-right" role="separator" tabIndex={0} aria-label={t("sidebar.resize")}
      data-file-sidebar-corner="" data-dragging={draft !== null ? "" : undefined}
      onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={stopDrag} onPointerCancel={stopDrag} onKeyDown={keyDrag} />}
  </aside>;
  return <>
    <div hidden={hidden} className="pointer-events-none absolute z-20 flex flex-col items-start gap-2" style={style} data-file-sidebar-room="">
      {/* The sidebar's toolbar: the tool strip's surface, padding and tiles, on the strip's line. */}
      {phone && tiles.length ? <div role="group" aria-label={t("sidebar.label")} data-file-sidebar-tools=""
        className={cn("pointer-events-auto inline-flex shrink-0 items-center rounded-md p-1", FLOATING_CHROME_SURFACE_CLASS)}>
        <ToolbarButton label={t("sidebar.toggle")} tooltipSide="bottom" className={cn(TOUCH_STRIP_BUTTON_CLASS, "relative")} active={Boolean(open)} aria-pressed={Boolean(open)}
          onClick={togglePanel} data-file-sidebar-toggle=""><Menu aria-hidden="true" />
          {/* Any section off its default, the panel's one tile says so too. */}
          {tiles.some(tile => tile.changed) ? <ChangedDot className="right-1.5 top-1.5" /> : null}</ToolbarButton>
      </div> : null}
      {tiles.length && !phone ? <div role="group" aria-label={t("sidebar.label")} data-file-sidebar-tools=""
        className={cn("pointer-events-auto inline-flex shrink-0 items-center gap-1 rounded-md p-1", FLOATING_CHROME_SURFACE_CLASS)}>
        {tiles.map(({ id, label, Icon, changed }) => <ToolbarButton key={id} label={label} tooltipSide="bottom" className={cn(STRIP_BUTTON_CLASS, changed && "relative")}
          active={open === id} aria-pressed={open === id} onClick={() => { if (open !== id) controls.used(`sidebar_${id}`); toggle(id); }} data-file-sidebar-tool={id} data-changed={changed ? "" : undefined}>
          <Icon aria-hidden="true" />
          {changed ? <ChangedDot /> : null}
        </ToolbarButton>)}
      </div> : null}
      {/* The panel under it, the open section's; closed, its sections stay mounted out of sight. It
          slides in from the left as a section opens with none open before, and back out as the last
          one closes; from one section to another it stays where it is. */}
      <div ref={room} className="relative min-h-0 w-full flex-1">{aside}</div>
    </div>
  </>;
}
