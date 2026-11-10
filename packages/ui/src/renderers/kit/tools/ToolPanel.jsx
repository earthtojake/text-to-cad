import { useCallback, useContext, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { cn } from "@cad/ui/utils";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { capturePointer, releasePointer } from "../../../lib/pointerCapture.js";
import ResizeGrip from "./ResizeGrip.jsx";
import { ToolStackContext } from "./ToolStack.jsx";
import { TOOL_PANEL_WIDTH, clampToolPanelHeight, clampToolPanelWidth } from "./toolStackLayout.js";
import { useI18n } from "@cad/ui/i18n";

/**
 * How the panels open together share a stack too short for all of them at their height
 * (`RendererShell.jsx` bounds the stack by the viewer; a resizable panel opens capped at all of
 * it). A `"fixed"` panel keeps its height. A `"tree"` panel gives way first and scrolls inside
 * itself; the `"details"` panels give way once the tree has, each in proportion to its height.
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
 * Every panel's heading text: the size and weight of Display's section headings
 * (`FILE_SHEET_SECTION_HEADING_CLASSES`, 11px), so every heading in the stack reads alike.
 */
export const TOOL_PANEL_HEADING_TEXT_CLASS = "text-tiny font-normal leading-4 text-foreground";

/** A panel header's small icon button: the chevron, the X, and a tool's settings menu (`ToolModeMenu.jsx`'s `ToolSettingsMenu`). */
export const TOOL_PANEL_BUTTON_CLASS = "flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";

function CollapseButton({ panel, className = "" }) {
  const { t } = useI18n();
  return <button type="button" aria-label={t(panel.collapsed ? "panel.expand" : "panel.collapse", { name: panel.label.toLowerCase() })} aria-expanded={!panel.collapsed}
    data-tool-panel-collapse="" className={cn(TOOL_PANEL_BUTTON_CLASS, className)} onClick={panel.toggle}>
    {/* Down to open a folded panel, up to fold an open one. */}
    {panel.collapsed ? <ChevronDown className="size-3" aria-hidden="true" data-chevron="down" /> : <ChevronUp className="size-3" aria-hidden="true" data-chevron="up" />}
  </button>;
}

// An X comes in lightly as it appears (a kept effect set, a pose moved off its default): a short
// fade and grow, none under reduced motion.
const REVEAL_CLASS = "animate-in fade-in-0 zoom-in-75 duration-150 motion-reduce:animate-none";

/**
 * One panel of the tool stack under the strip: a kept effect's controls, or what the tool in
 * hand shows (a model tree and the Reference for a selection, a set of joints). On the stack's
 * translucent surface, exactly its content's height — up to its cap, if it has one — never
 * padded to a minimum.
 *
 * Two kinds. A fixed panel (the default) is exactly `TOOL_PANEL_WIDTH` wide and its content's
 * height. A `resizable` panel (a tall one, the tree's) is the person's to size, under its
 * `id`: it opens at that width and capped at the stack's height, and the grip at its
 * bottom-right corner (`ResizeGrip.jsx`, Quick Edit's) moves only it — wider (never narrower than
 * the one width) and its cap up or down — by pointer or by keyboard (arrows by 16px; Home and End
 * to the bounds), written back once when the gesture lets go. A cap is never a floor: a short tree
 * is its rows.
 *
 * A panel folds to its first row and unfolds again, by a chevron at that row's trailing end
 * (down to open, up to fold); folded content stays mounted and keeps working. `collapsible={false}`
 * for a panel with nothing to fold away (a tree, a row of buttons, or one with an X instead). A
 * panel's first row is, in order: its heading (`title`, with a `summary`, the chevron and an X when
 * it has something to remove); its `header` (a tree's filter); or its content's own first row. A
 * folding panel without a heading or a header shows its `name` beside the chevron, and has no grip
 * while folded: there is no height to set. Which panels are folded is the person's
 * (`ToolStack.jsx`), by `id`, across files.
 *
 * `hidden` keeps a panel mounted while its tool is not up, so a tree keeps its expansion, filter
 * and scroll across a trip to another tool. `header` never scrolls; the body under it does, for a
 * panel that gives way. `lead`: the panel of the tool in hand, drawn at the top of the stack above every kept
 * panel, wherever it sits among them.
 *
 * @param {{ id: string, title?: import("react").ReactNode, name?: string, label: string, summary?: import("react").ReactNode,
 *   actions?: import("react").ReactNode, header?: import("react").ReactNode, collapsible?: boolean, onClose?: (() => void) | null, closeLabel?: string,
 *   fit?: "fixed" | "tree" | "details", resizable?: boolean, hidden?: boolean, defaultCollapsed?: boolean,
 *   lead?: boolean, children?: import("react").ReactNode }} props
 *   `label` names the panel for assistive technology ("Clip controls"), with a heading or
 *   without; the chevron, the X and the grip take their names from it, unless the X says
 *   what it does itself (`closeLabel`, "Clear selection").
 */
export default function ToolPanel({ id, title = null, name = "", label, summary = null, actions = null, header = null, collapsible = true, onClose = null, closeLabel = "",
  fit = "fixed", resizable = false, hidden = false, defaultCollapsed = false, lead = false, children }) {
  const { t } = useI18n();
  const stack = useContext(ToolStackContext);
  const kept = Boolean(stack && id);
  // In a view's panel (`kit/shell/FlatPanel.jsx`) a panel is one of its tabs: its name the tab's, its
  // body the tab's page, shown while its tab is open (or while the panel's search is up, under its
  // name, left out when it holds no match). It draws no heading and pads nothing: the panel's body
  // stands its rows on the panel's lines.
  const tabbed = Boolean(stack?.tabbed);
  if (tabbed) collapsible = false;
  const registerTab = tabbed ? stack.register : null;
  const tabName = typeof title === "string" && title ? title : name || label;
  useLayoutEffect(() => (registerTab && id && !hidden ? registerTab(id, tabName) : undefined), [registerTab, id, hidden, tabName]);
  // Folded: the person's, kept by the stack across files; a panel drawn alone keeps its own.
  const [ownCollapsed, setOwnCollapsed] = useState(defaultCollapsed);
  const collapsed = collapsible && (kept ? stack.collapsed(id, defaultCollapsed) : ownCollapsed);
  const toggle = useCallback(() => {
    if (kept) stack.settle(id, { collapsed: !collapsed, fallback: defaultCollapsed }); else setOwnCollapsed(value => !value);
  }, [kept, stack, id, collapsed, defaultCollapsed]);
  const folding = useMemo(() => collapsible ? { label, collapsed, toggle } : null, [collapsible, collapsed, toggle, label]);

  // The size: dragged (`draft`), then as the person left it, then the defaults — every panel's
  // width, and the stack's cap for this id.
  const sized = resizable && Boolean(id) && !tabbed;
  const [draft, setDraft] = useState(null);
  const [ownSize, setOwnSize] = useState({});
  const size = sized ? { ...(kept ? stack.size(id) : ownSize), ...draft } : {};
  const clampWidth = value => clampToolPanelWidth(value, stack?.viewerWidth || window.innerWidth);
  const clampHeight = value => clampToolPanelHeight(value, stack?.room() || Infinity);
  const width = tabbed ? undefined : size.width ? clampWidth(size.width) : TOOL_PANEL_WIDTH;
  const cap = sized ? size.height ?? stack?.defaultHeight() ?? null : null;
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
    capturePointer(event.currentTarget, event.pointerId);
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
    releasePointer(event.currentTarget, event.pointerId);
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
  const floored = fit !== "fixed" && !tabbed && !collapsed && !hidden;
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
  // A folding panel's heading row is its fold's, wherever it is pressed but on another of its
  // buttons, under one hover; the chevron is the row's way in from the keyboard.
  const foldRow = folding ? {
    onClick: event => { if (!(event.target instanceof Element) || !event.target.closest("button")) folding.toggle(); },
    className: "cursor-pointer select-none hover:bg-accent/50",
    "data-tool-panel-fold-row": "",
  } : null;

  const closeButton = onClose ? <button type="button" aria-label={closeLabel || t("panel.close", { name: label.toLowerCase() })}
    className={cn(TOOL_PANEL_BUTTON_CLASS, REVEAL_CLASS)} onClick={onClose}><X className="size-3" aria-hidden="true" /></button> : null;
  const heading = title ? <div {...foldRow} className={cn("flex min-h-7 shrink-0 items-center justify-end gap-0.5 pl-2 pr-1", foldRow?.className)} data-tool-panel-heading="">
    <h3 className={cn("min-w-0 truncate", TOOL_PANEL_HEADING_TEXT_CLASS)}>{title}</h3>
    {summary ? <span className="ml-2 shrink-0 text-tiny text-muted-foreground">{summary}</span> : null}
    <span className="min-w-0 flex-1" aria-hidden="true" />
    {actions}
    {folding ? <CollapseButton panel={folding} className="hover:bg-transparent" /> : null}
    {closeButton}
  </div>
    // No heading of its own: a folding panel's name stands in for one, beside its chevron.
    : folding ? <div {...foldRow} className={cn("flex min-h-7 shrink-0 items-center gap-0.5 pl-2 pr-1", foldRow.className)} data-tool-panel-heading="">
      <h3 className={cn("min-w-0 flex-1 truncate", TOOL_PANEL_HEADING_TEXT_CLASS)}>{name || label}</h3>
      <CollapseButton panel={folding} className="hover:bg-transparent" />
    </div> : null;

  const dragging = draft !== null;
  if (tabbed) {
    const searching = stack.searching;
    return <section ref={section} aria-label={label} hidden={hidden || !(searching || stack.activeSection === id)} role={stack.single ? "region" : "tabpanel"}
      id={`flat-panel-body-${id}`} aria-labelledby={stack.single ? undefined : `flat-panel-tab-${id}`} data-flat-panel-section={id} data-tool-panel-id={id || undefined} data-tool-panel={fit}
      className={cn("min-w-0 text-tiny", searching && "not-has-[[data-flat-panel-hit]]:hidden")}>
      {searching && !stack.single ? <h3 className="flex h-6 items-center px-2 text-tiny text-muted-foreground">{tabName}</h3> : null}
      <div ref={body} data-tool-panel-body="" className="min-w-0">
        <div ref={content} className="flow-root">{children}</div>
      </div>
    </section>;
  }
  return <section ref={section} aria-label={label} hidden={hidden} data-tool-panel={fit} data-tool-panel-id={id || undefined}
    data-collapsed={collapsed ? "" : undefined} data-resizable={sized ? "" : undefined} data-tool-panel-lead={lead ? "" : undefined}
    className={cn("pointer-events-auto relative flex max-w-full flex-col rounded-md text-tiny", FLOATING_CHROME_SURFACE_CLASS, collapsed ? "shrink-0" : FIT[fit])}
    style={{ width, maxHeight: collapsed || cap === null ? undefined : `${cap}px`, minHeight, order: lead ? -1 : undefined }}>
    {heading}
    {/* Folded under a heading, the header (a tree's filter) goes with the body. */}
    {collapsed && heading ? null : header}
    {/* A panel that gives way scrolls in the chrome's one scroll region; a fixed one never scrolls. */}
    {fit === "fixed" ? <div ref={body} hidden={collapsed} data-tool-panel-body="" className="min-w-0 overflow-x-clip rounded-b-md">
      <div ref={content} className="flow-root">{children}</div>
    </div> : <ScrollArea hidden={collapsed} className="min-w-0 flex-1 rounded-b-md" viewportRef={body} viewportProps={{ "data-tool-panel-body": "" }}>
      <div ref={content} className="flow-root">{children}</div>
    </ScrollArea>}
    {/* The person's to size, from its bottom-right corner alone: Quick Edit's grip, inside the
        panel's border, moving both its width and its cap. A folded panel has none: there is no
        height to set. */}
    {sized && !collapsed ? <ResizeGrip corner="bottom-right" role="separator" tabIndex={0} aria-label={t("panel.resize", { name: label.toLowerCase() })}
      data-tool-panel-corner-handle="" data-dragging={dragging ? "" : undefined}
      onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={stopDrag} onPointerCancel={stopDrag} onKeyDown={keyDrag} /> : null}
  </section>;
}
