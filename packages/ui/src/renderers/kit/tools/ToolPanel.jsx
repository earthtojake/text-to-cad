import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { cn } from "@text-to-cad/ui/utils";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { FLOATING_CHROME_SURFACE_CLASS } from "./floatingSurface.js";
import { ToolStackContext } from "./ToolStack.jsx";
import { TOOL_PANEL_MIN_HEIGHT, TOOL_PANEL_WIDTH, clampToolPanelHeight, clampToolPanelWidth } from "./toolStackLayout.js";

/**
 * How a panel of the tool stack answers a viewer too short for every panel at its height
 * (`RendererShell.jsx` bounds the stack by the viewer). A `"fixed"` panel keeps its height. A
 * `"tree"` panel gives way first and scrolls inside itself; a `"details"` panel gives way once the
 * tree has. On mobile a tree takes at most 40% of the stack's height, however tall it is.
 * The shrink factors are orders of magnitude apart, so the tree absorbs nearly all of the
 * overflow until it reaches its floor and a fixed panel never scrolls a few pixels meanwhile.
 */
const FIT = Object.freeze({
  fixed: "shrink-0",
  tree: "shrink-[100000]",
  details: "shrink",
});
// How far a panel gives way before the next one does: never below its content's own height (a
// panel is never taller than what it holds, so a short one keeps no empty space), and otherwise
// room for its first row and a few more.
const FLOOR = Object.freeze({ tree: 128, details: 96 });
const KEY_NUDGE_PX = 16;
// Every handle: a hit area and a cursor, nothing drawn but a ring for the keyboard.
const HANDLE_CLASS = "pointer-events-auto absolute z-10 touch-none rounded-full outline-none before:absolute before:rounded-full before:bg-transparent focus-visible:before:bg-ring";
/**
 * Every panel's heading text: the size and weight of the Display panel's section headings
 * (`FILE_SHEET_SECTION_HEADING_CLASSES`, 11px), so every heading in the stack reads alike.
 */
export const TOOL_PANEL_HEADING_TEXT_CLASS = "text-tiny font-normal leading-4 text-foreground";

/** A panel header's small icon button: the chevron, the X, and a tool's mode menu (`ToolModeMenu.jsx`). */
export const TOOL_PANEL_BUTTON_CLASS = "flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";

const ToolPanelContext = createContext(null);

function CollapseButton({ panel, className }) {
  return <button type="button" aria-label={`${panel.collapsed ? "Expand" : "Collapse"} ${panel.label.toLowerCase()}`} aria-expanded={!panel.collapsed}
    data-tool-panel-collapse="" className={cn(TOOL_PANEL_BUTTON_CLASS, className)} onClick={panel.toggle}>
    {/* Down to open a folded panel, up to fold an open one. */}
    {panel.collapsed ? <ChevronDown className="size-3" aria-hidden="true" data-chevron="down" /> : <ChevronUp className="size-3" aria-hidden="true" data-chevron="up" />}
  </button>;
}

/**
 * The chevron that folds the panel it is drawn in to its first row, for a panel whose first row
 * is its content's own: a tree's filter row, Display's first heading, a set of joints' Pose row.
 * Drawn anywhere inside a collapsible `ToolPanel`, at that row's trailing end; nothing outside one.
 */
export function ToolPanelCollapse({ className }) {
  const panel = useContext(ToolPanelContext);
  const place = panel?.place;
  useLayoutEffect(() => place?.(), [place]);
  return panel ? <CollapseButton panel={panel} className={className} /> : null;
}

/**
 * One panel of the tool stack under the strip: a kept effect's controls, or what the tool in
 * hand shows (a model tree and the Reference for a selection, a set of joints). On the stack's
 * translucent surface, exactly its content's height — up to its cap, if it has one — never
 * padded to a minimum.
 *
 * Two kinds. A fixed panel (the default) is exactly `TOOL_PANEL_WIDTH` wide and its content's
 * height. A `resizable` panel (the tree, Position) is the person's to size, under its `id`: it
 * opens at that width and the stack's default cap for that id, and three handles on it — its
 * right edge (width, only ever wider), its bottom edge (height) and its bottom-right corner
 * (both) — move only it, by pointer or by keyboard (arrows by 16px; Home and End on an edge),
 * written back once when the gesture lets go. A cap is never a floor: a short tree is its rows.
 * `maxHeight` caps a fixed panel (the Reference) at a height that is not the person's.
 *
 * A panel folds to its first row and unfolds again, by a chevron at that row's trailing end
 * (down to open, up to fold); folded content stays mounted and keeps working, so a tree keeps its
 * expansion, filter and scroll. `collapsible={false}` for a panel with nothing to fold away (a
 * row of buttons). A panel's first row is, in order: its heading (`title`, with a `summary`, the chevron and
 * an X when it has something to remove); its `header` (a tree's filter, which carries a
 * `ToolPanelCollapse`); or its content's own first row, which carries one too. Folded, a panel
 * without a heading or a header shows its `name` beside the chevron, keeps its width handle and
 * loses the other two. Which panels are folded is the person's (`ToolStack.jsx`), by `id`, across files.
 *
 * `hidden` keeps a panel mounted while its tool is not up, so a tree keeps its expansion,
 * filter and scroll across a trip to another tool. `header` never scrolls; the body under it
 * does, for a panel that gives way.
 *
 * @param {{ id: string, title?: import("react").ReactNode, name?: string, label: string, summary?: import("react").ReactNode,
 *   actions?: import("react").ReactNode,
 *   header?: import("react").ReactNode, collapsible?: boolean, onClose?: (() => void) | null, closeLabel?: string,
 *   fit?: "fixed" | "tree" | "details", resizable?: boolean, widthFrom?: string | null, maxHeight?: number | null, hidden?: boolean, defaultCollapsed?: boolean,
 *   children?: import("react").ReactNode }} props
 *   `label` names the panel for assistive technology ("Clip controls"), with a heading or
 *   without; the chevron, the X and the handles take their names from it, unless the X says
 *   what it does itself (`closeLabel`, "Clear selection"). `widthFrom`: a fixed panel that takes
 *   the width of the resizable panel with that id, live while it is dragged ("tree": Reference
 *   sits under the tree at its width), keeping its own height rules.
 */
export default function ToolPanel({ id, title = null, name = "", label, summary = null, actions = null, header = null, collapsible = true, onClose = null, closeLabel = "",
  fit = "fixed", resizable = false, widthFrom = null, maxHeight = null, hidden = false, defaultCollapsed = false, children }) {
  const stack = useContext(ToolStackContext);
  const kept = Boolean(stack && id);
  // Folded: the person's, kept by the stack across files; a panel drawn alone keeps its own.
  const [ownCollapsed, setOwnCollapsed] = useState(defaultCollapsed);
  const collapsed = collapsible && (kept ? stack.collapsed(id, defaultCollapsed) : ownCollapsed);
  const toggle = useCallback(() => {
    if (kept) stack.settle(id, { collapsed: !collapsed, fallback: defaultCollapsed }); else setOwnCollapsed(value => !value);
  }, [kept, stack, id, collapsed, defaultCollapsed]);
  // Whether the content carries the chevron in its own first row (`ToolPanelCollapse`).
  const [placed, setPlaced] = useState(0);
  const place = useCallback(() => { setPlaced(count => count + 1); return () => setPlaced(count => count - 1); }, []);
  const panel = useMemo(() => collapsible ? { collapsed, toggle, label, place } : null, [collapsible, collapsed, toggle, label, place]);

  // The size: dragged (`draft`), then as the person left it, then the defaults — every panel's
  // width, and the stack's cap for this id.
  const sized = resizable && Boolean(id);
  const [draft, setDraft] = useState(null);
  const [ownSize, setOwnSize] = useState({});
  const size = sized ? { ...(kept ? stack.size(id) : ownSize), ...draft } : {};
  const clampWidth = value => clampToolPanelWidth(value, stack?.viewerWidth || window.innerWidth);
  const clampHeight = value => clampToolPanelHeight(value, stack?.room() || Infinity);
  const borrowed = !sized && widthFrom ? stack?.widthOf(widthFrom) : undefined;
  const width = size.width ? clampWidth(size.width) : borrowed ? clampWidth(borrowed) : TOOL_PANEL_WIDTH;
  const cap = sized ? size.height ?? stack?.defaultHeight(id) ?? null : maxHeight;
  // One gesture's outcome, written once: a width, a cap, or both.
  const settle = change => {
    setDraft(null);
    if (kept) stack.draft(id, null);
    if (!Object.keys(change).length) return;
    if (kept) stack.settle(id, change); else setOwnSize(current => ({ ...current, ...change }));
  };

  const section = useRef(null), body = useRef(null), content = useRef(null);
  const drag = useRef(null);
  // What a gesture starts from: the size on screen, which is less than the cap for a short panel.
  const drawn = () => {
    const box = section.current?.getBoundingClientRect();
    return { width: box?.width ?? 0, height: Math.min(cap ?? Infinity, box?.height ?? 0) };
  };
  const startDrag = (event, axes) => {
    if (event.button !== 0) return;
    event.preventDefault();
    drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, from: drawn(), axes, next: null };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const moveDrag = event => {
    const current = drag.current;
    if (current?.pointerId !== event.pointerId) return;
    current.next = {
      ...(current.axes.x ? { width: clampWidth(current.from.width + event.clientX - current.x) } : {}),
      ...(current.axes.y ? { height: clampHeight(current.from.height + event.clientY - current.y) } : {}),
    };
    setDraft(current.next);
    if (kept) stack.draft(id, current.next);
  };
  const stopDrag = event => {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    settle(current.next || {});
  };
  // Arrows nudge by 16px; on an edge, Home and End go to the bound.
  const keyDrag = (event, axes) => {
    const from = drawn(), ends = !(axes.x && axes.y), change = {};
    if (axes.x) {
      const to = { ArrowLeft: from.width - KEY_NUDGE_PX, ArrowRight: from.width + KEY_NUDGE_PX, ...(ends ? { Home: 0, End: Infinity } : {}) }[event.key];
      if (to !== undefined) change.width = clampWidth(to);
    }
    if (axes.y) {
      const to = { ArrowUp: from.height - KEY_NUDGE_PX, ArrowDown: from.height + KEY_NUDGE_PX, ...(ends ? { Home: 0, End: Infinity } : {}) }[event.key];
      if (to !== undefined) change.height = clampHeight(to);
    }
    if (!Object.keys(change).length) return;
    event.preventDefault();
    settle(change);
  };
  const handle = (axes, props) => <div role="separator" tabIndex={0} {...props}
    onPointerDown={event => startDrag(event, axes)} onPointerMove={moveDrag} onPointerUp={stopDrag} onPointerCancel={stopDrag}
    onKeyDown={event => keyDrag(event, axes)} />;

  // The floor it gives way to: its content's own height when that is less (`FLOOR`).
  const floored = fit !== "fixed" && !collapsed && !hidden;
  const [natural, setNatural] = useState(null);
  useLayoutEffect(() => {
    if (!floored || !section.current || !body.current || !content.current) return undefined;
    const measure = () => setNatural(Math.ceil(section.current.offsetHeight - body.current.clientHeight + content.current.offsetHeight));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(section.current);
    observer.observe(content.current);
    return () => observer.disconnect();
  }, [floored]);
  const minHeight = floored && natural !== null ? Math.min(natural, FLOOR[fit], cap === null ? Infinity : cap) : undefined;

  const heading = title ? <div className="flex min-h-7 shrink-0 items-center justify-end gap-0.5 pl-2 pr-1" data-tool-panel-heading="">
    <h3 className={cn("min-w-0 truncate", TOOL_PANEL_HEADING_TEXT_CLASS)}>{title}</h3>
    {summary ? <span className="ml-2 shrink-0 text-tiny text-muted-foreground">{summary}</span> : null}
    <span className="min-w-0 flex-1" aria-hidden="true" />
    {actions}
    {panel ? <CollapseButton panel={panel} /> : null}
    {onClose ? <button type="button" aria-label={closeLabel || `Close ${label.toLowerCase()}`}
      className={TOOL_PANEL_BUTTON_CLASS} onClick={onClose}><X className="size-3" aria-hidden="true" /></button> : null}
  </div>
    // No heading of its own: while its content's first row is out of sight (folded) or carries no
    // chevron, the panel's name stands in for it.
    : panel && (!placed || (collapsed && !header)) ? <div className="flex min-h-7 shrink-0 items-center gap-0.5 pl-2 pr-1" data-tool-panel-heading="">
      <h3 className={cn("min-w-0 flex-1 truncate", TOOL_PANEL_HEADING_TEXT_CLASS)}>{name || label}</h3>
      <CollapseButton panel={panel} />
    </div> : null;

  const lower = label.toLowerCase();
  return <section ref={section} aria-label={label} hidden={hidden} data-tool-panel={fit} data-tool-panel-id={id || undefined}
    data-collapsed={collapsed ? "" : undefined} data-resizable={sized ? "" : undefined}
    // Folded to a filter row, the row's rule under it has nothing under it to divide off.
    className={cn("pointer-events-auto relative flex max-w-full flex-col rounded-md text-tiny", FLOATING_CHROME_SURFACE_CLASS, collapsed ? "shrink-0" : FIT[fit],
      "data-[collapsed]:[&_[data-slot=tree-filter]]:shadow-none")}
    style={{ width, maxHeight: collapsed || cap === null ? undefined : `${cap}px`, minHeight }}>
    <ToolPanelContext.Provider value={panel}>
      {heading}
      {/* Typing into a folded panel's filter opens it: what the filter finds is in the body. The
          keystroke is the filter's first — it lands as it would in an open panel — and the panel
          opens once it has: opening writes the viewer's preferences, whose store re-renders at once,
          and doing that mid-keystroke would put the box back to what it held before the key. */}
      {header ? <div className="contents" onInput={event => {
        if (!collapsed || !(event.target instanceof HTMLInputElement) || !event.target.value) return;
        queueMicrotask(() => { if (kept) stack.settle(id, { collapsed: false, fallback: defaultCollapsed }); else setOwnCollapsed(false); });
      }}>{header}</div> : null}
      {/* A panel that gives way scrolls in the chrome's one scroll region; a fixed one never scrolls. */}
      {fit === "fixed" ? <div ref={body} hidden={collapsed} data-tool-panel-body="" className="min-w-0 overflow-x-clip rounded-b-md">
        <div ref={content} className="flow-root">{children}</div>
      </div> : <ScrollArea hidden={collapsed} className="min-w-0 flex-1 rounded-b-md" viewportRef={body} viewportProps={{ "data-tool-panel-body": "" }}>
        <div ref={content} className="flow-root">{children}</div>
      </ScrollArea>}
    </ToolPanelContext.Provider>
    {/* The person's to size: a handle ON each edge it grows along (centred on it, an 8px hit
        area) and one on the corner between them, 12px, reaching 5px past the panel: the stack's
        column leaves that much room (`ToolStack.jsx`). A folded panel keeps only its width's. */}
    {sized ? handle({ x: true }, { "aria-label": `Resize ${lower} width`, "aria-orientation": "vertical", "data-tool-panel-width-handle": "",
      "data-dragging": draft?.width === undefined ? undefined : "", "aria-valuemin": TOOL_PANEL_WIDTH, "aria-valuemax": clampWidth(Infinity), "aria-valuenow": width,
      className: cn(HANDLE_CLASS, "inset-y-0 left-full w-2 -translate-x-1/2 cursor-col-resize before:inset-y-1 before:left-1/2 before:w-0.5 before:-translate-x-1/2") }) : null}
    {sized && !collapsed ? <>
      {handle({ y: true }, { "aria-label": `Resize ${lower} height`, "aria-orientation": "horizontal", "data-tool-panel-height-handle": "",
        "data-dragging": draft?.height === undefined ? undefined : "", "aria-valuemin": TOOL_PANEL_MIN_HEIGHT, "aria-valuemax": clampHeight(Infinity), "aria-valuenow": cap,
        className: cn(HANDLE_CLASS, "-inset-x-px top-full h-2 -translate-y-1/2 cursor-row-resize before:inset-x-1 before:top-1/2 before:h-0.5 before:-translate-y-1/2") })}
      {handle({ x: true, y: true }, { "aria-label": `Resize ${lower}`, "data-tool-panel-corner-handle": "", "data-dragging": draft === null ? undefined : "",
        className: cn(HANDLE_CLASS, "left-full top-full z-20 size-3 -translate-x-1/2 -translate-y-1/2 cursor-nwse-resize before:inset-[3px]") })}
    </> : null}
  </section>;
}
