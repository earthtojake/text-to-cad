import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, X } from "lucide-react";
import { cn } from "@text-to-cad/ui/utils";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { FLOATING_CHROME_SURFACE_CLASS } from "./floatingSurface.js";
import ResizeGrip from "./ResizeGrip.jsx";
import { ToolStackContext } from "./ToolStack.jsx";
import { TOOL_PANEL_WIDTH, clampToolPanelHeight, clampToolPanelWidth } from "./toolStackLayout.js";

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
/**
 * Every panel's heading text: the size and weight of the Display panel's section headings
 * (`FILE_SHEET_SECTION_HEADING_CLASSES`, 11px), so every heading in the stack reads alike.
 */
export const TOOL_PANEL_HEADING_TEXT_CLASS = "text-tiny font-normal leading-4 text-foreground";

/** A panel header's small icon button: the chevron, the X, and a tool's mode menu (`ToolModeMenu.jsx`). */
export const TOOL_PANEL_BUTTON_CLASS = "flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";

// What the panel's content reads of it: how to close it from its own first row (`ToolPanelClose`), and its name.
const ToolPanelContext = createContext(null);

/**
 * A panel's full-row action at its foot, under everything it holds: Copy under the Reference
 * (Copy All with several references) and Copy Drawing under the drawing controls. `shortcut` is the
 * key that does the same from the viewer (⌘C). A press whose `onClick` answers true says "Copied",
 * with a tick where the shortcut was, for a moment.
 * @param {{ label: string, shortcut?: string, disabled?: boolean, onClick(): unknown }} props
 */
export function ToolPanelFooterButton({ label, shortcut = "", disabled = false, onClick }) {
  const keys = shortcut ? shortcut.replace("⌘", "Meta+").replace("Ctrl+", "Control+") : undefined;
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!done) return undefined;
    const timer = setTimeout(() => setDone(false), 1200);
    return () => clearTimeout(timer);
  }, [done]);
  return <button type="button" aria-label={label} aria-keyshortcuts={keys} disabled={disabled} data-tool-panel-footer-button=""
    className="flex h-7 w-full shrink-0 items-center justify-center gap-2 rounded-b-md border-t border-border text-tiny text-foreground hover:bg-accent/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/45 disabled:opacity-50"
    onClick={async () => { if (await onClick()) setDone(true); }}>
    <span>{done ? "Copied" : label}</span>
    {done ? <Check className="size-3" aria-hidden="true" /> : shortcut ? <kbd aria-hidden="true" className="font-sans text-micro text-muted-foreground">{shortcut}</kbd> : null}
  </button>;
}

function CollapseButton({ panel, className }) {
  return <button type="button" aria-label={`${panel.collapsed ? "Expand" : "Collapse"} ${panel.label.toLowerCase()}`} aria-expanded={!panel.collapsed}
    data-tool-panel-collapse="" className={cn(TOOL_PANEL_BUTTON_CLASS, className)} onClick={panel.toggle}>
    {/* Down to open a folded panel, up to fold an open one. */}
    {panel.collapsed ? <ChevronDown className="size-3" aria-hidden="true" data-chevron="down" /> : <ChevronUp className="size-3" aria-hidden="true" data-chevron="up" />}
  </button>;
}

/**
 * The X that closes the panel it is drawn in, for a panel whose first row is its content's own:
 * a tree's filter row (a `closable` panel: it goes, kept as it is, until the tool it belongs to
 * brings it back — `RendererShell.jsx`, a press on that tool while it is up), or Display's first
 * heading (a panel with `onClose` and no heading of its own). Drawn at that row's trailing end,
 * inside such a `ToolPanel`; nothing outside one.
 */
export function ToolPanelClose({ className }) {
  const panel = useContext(ToolPanelContext);
  return panel?.close ? <button type="button" aria-label={panel.closeLabel || `Close ${panel.label.toLowerCase()}`} data-tool-panel-close=""
    className={cn(TOOL_PANEL_BUTTON_CLASS, className)} onClick={panel.close}>
    <X className="size-3" aria-hidden="true" />
  </button> : null;
}

/**
 * One panel of the tool stack under the strip: a kept effect's controls, or what the tool in
 * hand shows (a model tree and the Reference for a selection, a set of joints). On the stack's
 * translucent surface, exactly its content's height — up to its cap, if it has one — never
 * padded to a minimum.
 *
 * Two kinds. A fixed panel (the default) is exactly `TOOL_PANEL_WIDTH` wide and its content's
 * height. A `resizable` panel (the tree, the Reference, Position) is the person's to size, under its
 * `id`: it opens at that width and the stack's default cap for that id, and the grip at its
 * bottom-right corner (`ResizeGrip.jsx`, Quick Edit's) moves only it — wider (never narrower than
 * the one width) and its cap up or down — by pointer or by keyboard (arrows by 16px; Home and End
 * to the bounds), written back once when the gesture lets go. A cap is never a floor: a short tree
 * is its rows.
 *
 * A panel folds to its first row and unfolds again, by a chevron at that row's trailing end
 * (down to open, up to fold); folded content stays mounted and keeps working. `collapsible={false}`
 * for a panel with nothing to fold away (a row of buttons, or one with an X instead). A panel's
 * first row is, in order: its heading (`title`, with a `summary`, the chevron and an X when it has
 * something to remove); its `header` (a tree's filter, which carries a `ToolPanelClose`); or its
 * content's own first row, which carries the X of a panel with `onClose` and no `title`
 * (`ToolPanelClose`: Display's). A folding panel without a heading or a header shows its `name`
 * beside the chevron, and has no grip while folded: there is no height to set. Which panels are
 * folded is the person's (`ToolStack.jsx`), by `id`, across files.
 *
 * `closable`: the tree's. Its X (`ToolPanelClose`) puts the panel away — `hidden`, kept mounted —
 * and the tool it belongs to brings it back; whether it is closed is the person's too, by `id`,
 * starting closed on a phone and wherever the tool it belongs to says the file starts it closed
 * (a single part's: `toolPanelClosed`). `hidden` keeps a panel mounted while its tool is
 * not up, so a tree keeps its expansion, filter and scroll across a trip to another tool. `header`
 * never scrolls; the body under it does, for a panel that gives way; `footer` (a
 * `ToolPanelFooterButton`) is under the body and never scrolls either.
 *
 * @param {{ id: string, title?: import("react").ReactNode, name?: string, label: string, summary?: import("react").ReactNode,
 *   actions?: import("react").ReactNode,
 *   header?: import("react").ReactNode, footer?: import("react").ReactNode, collapsible?: boolean, closable?: boolean, onClose?: (() => void) | null, closeLabel?: string,
 *   fit?: "fixed" | "tree" | "details", resizable?: boolean, hidden?: boolean, defaultCollapsed?: boolean,
 *   children?: import("react").ReactNode }} props
 *   `label` names the panel for assistive technology ("Clip controls"), with a heading or
 *   without; the chevron, the X and the grip take their names from it, unless the X says
 *   what it does itself (`closeLabel`, "Clear selection").
 */
export default function ToolPanel({ id, title = null, name = "", label, summary = null, actions = null, header = null, footer = null, collapsible = true, closable = false, onClose = null, closeLabel = "",
  fit = "fixed", resizable = false, hidden = false, defaultCollapsed = false, children }) {
  const stack = useContext(ToolStackContext);
  const kept = Boolean(stack && id);
  // Folded: the person's, kept by the stack across files; a panel drawn alone keeps its own.
  const [ownCollapsed, setOwnCollapsed] = useState(defaultCollapsed);
  const collapsed = collapsible && (kept ? stack.collapsed(id, defaultCollapsed) : ownCollapsed);
  const toggle = useCallback(() => {
    if (kept) stack.settle(id, { collapsed: !collapsed, fallback: defaultCollapsed }); else setOwnCollapsed(value => !value);
  }, [kept, stack, id, collapsed, defaultCollapsed]);
  // Closed: the person's as well, kept by the stack; a panel drawn alone keeps its own.
  const [ownClosed, setOwnClosed] = useState(false);
  const closed = closable && (kept ? stack.closed(id) : ownClosed);
  const close = useCallback(() => { if (kept) stack.settle(id, { closed: true }); else setOwnClosed(true); }, [kept, stack, id]);
  // The X the content's own first row carries (`ToolPanelClose`): a closable panel's, which the
  // stack keeps closed, or the `onClose` of a panel with no heading to draw it in.
  const contentClose = closable ? close : !title && onClose ? onClose : null;
  const panel = useMemo(() => collapsible || contentClose ? {
    label, closeLabel, ...(collapsible ? { collapsed, toggle } : {}), ...(contentClose ? { close: contentClose } : {})
  } : null, [collapsible, contentClose, collapsed, toggle, label, closeLabel]);
  const folding = collapsible ? panel : null;

  // The size: dragged (`draft`), then as the person left it, then the defaults — every panel's
  // width, and the stack's cap for this id.
  const sized = resizable && Boolean(id);
  const [draft, setDraft] = useState(null);
  const [ownSize, setOwnSize] = useState({});
  const size = sized ? { ...(kept ? stack.size(id) : ownSize), ...draft } : {};
  const clampWidth = value => clampToolPanelWidth(value, stack?.viewerWidth || window.innerWidth);
  const clampHeight = value => clampToolPanelHeight(value, stack?.room() || Infinity);
  const width = size.width ? clampWidth(size.width) : TOOL_PANEL_WIDTH;
  const cap = sized ? size.height ?? stack?.defaultHeight(id) ?? null : null;
  // One gesture's outcome, written once: a width, a cap, or both.
  const settle = change => {
    setDraft(null);
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
  // The corner moves both: the width and the cap, from where the panel is drawn.
  const startDrag = event => {
    if (event.button !== 0) return;
    event.preventDefault();
    drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, from: drawn(), next: null };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const moveDrag = event => {
    const current = drag.current;
    if (current?.pointerId !== event.pointerId) return;
    current.next = {
      width: clampWidth(current.from.width + event.clientX - current.x),
      height: clampHeight(current.from.height + event.clientY - current.y),
    };
    setDraft(current.next);
  };
  const stopDrag = event => {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    settle(current.next || {});
  };
  // Arrows nudge by 16px, Left/Right the width and Up/Down the cap; Home and End take both to
  // their bounds (the one width and the shortest cap; half the viewer and the stack's height).
  const keyDrag = event => {
    const from = drawn(), change = {};
    const width = { ArrowLeft: from.width - KEY_NUDGE_PX, ArrowRight: from.width + KEY_NUDGE_PX, Home: 0, End: Infinity }[event.key];
    const height = { ArrowUp: from.height - KEY_NUDGE_PX, ArrowDown: from.height + KEY_NUDGE_PX, Home: 0, End: Infinity }[event.key];
    if (width !== undefined) change.width = clampWidth(width);
    if (height !== undefined) change.height = clampHeight(height);
    if (!Object.keys(change).length) return;
    event.preventDefault();
    settle(change);
  };

  // The floor it gives way to: its content's own height when that is less (`FLOOR`).
  const floored = fit !== "fixed" && !collapsed && !hidden && !closed;
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
    {folding ? <CollapseButton panel={folding} /> : null}
    {onClose ? <button type="button" aria-label={closeLabel || `Close ${label.toLowerCase()}`}
      className={TOOL_PANEL_BUTTON_CLASS} onClick={onClose}><X className="size-3" aria-hidden="true" /></button> : null}
  </div>
    // No heading of its own: a folding panel's name stands in for one, beside its chevron.
    : folding ? <div className="flex min-h-7 shrink-0 items-center gap-0.5 pl-2 pr-1" data-tool-panel-heading="">
      <h3 className={cn("min-w-0 flex-1 truncate", TOOL_PANEL_HEADING_TEXT_CLASS)}>{name || label}</h3>
      <CollapseButton panel={folding} />
    </div> : null;

  const dragging = draft !== null;
  return <section ref={section} aria-label={label} hidden={hidden || closed} data-tool-panel={fit} data-tool-panel-id={id || undefined}
    data-collapsed={collapsed ? "" : undefined} data-closed={closed ? "" : undefined} data-resizable={sized ? "" : undefined}
    className={cn("pointer-events-auto relative flex max-w-full flex-col rounded-md text-tiny", FLOATING_CHROME_SURFACE_CLASS, collapsed ? "shrink-0" : FIT[fit])}
    style={{ width, maxHeight: collapsed || cap === null ? undefined : `${cap}px`, minHeight }}>
    <ToolPanelContext.Provider value={panel}>
      {heading}
      {header}
      {/* A panel that gives way scrolls in the chrome's one scroll region; a fixed one never scrolls. */}
      {fit === "fixed" ? <div ref={body} hidden={collapsed} data-tool-panel-body="" className="min-w-0 overflow-x-clip rounded-b-md">
        <div ref={content} className="flow-root">{children}</div>
      </div> : <ScrollArea hidden={collapsed} className="min-w-0 flex-1 rounded-b-md" viewportRef={body} viewportProps={{ "data-tool-panel-body": "" }}>
        <div ref={content} className="flow-root">{children}</div>
      </ScrollArea>}
      {footer && !collapsed ? footer : null}
    </ToolPanelContext.Provider>
    {/* The person's to size, from its bottom-right corner alone: Quick Edit's grip, inside the
        panel's border, moving both its width and its cap. A folded panel has none: there is no
        height to set. */}
    {sized && !collapsed ? <ResizeGrip corner="bottom-right" role="separator" tabIndex={0} aria-label={`Resize ${label.toLowerCase()}`}
      data-tool-panel-corner-handle="" data-dragging={dragging ? "" : undefined}
      onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={stopDrag} onPointerCancel={stopDrag} onKeyDown={keyDrag} /> : null}
  </section>;
}
