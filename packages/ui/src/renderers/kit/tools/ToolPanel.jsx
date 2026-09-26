import { useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import { FLOATING_SURFACE_CLASS } from "./floatingSurface.js";

/**
 * How a panel of the tool stack answers a viewer too short for every panel at its natural
 * height (`RendererShell.jsx` bounds the stack by the viewer). A `"fixed"` panel keeps its
 * height. A `"tree"` panel gives way first and scrolls inside itself, down to room for its
 * filter and a few rows; a `"details"` panel gives way once the tree has, down to a floor of
 * its own. On mobile a tree takes at most 40% of the stack's height, however tall it is.
 * The shrink factors are orders of magnitude apart, so the tree absorbs nearly all of the
 * overflow until it reaches its floor and a fixed panel never scrolls a few pixels meanwhile.
 */
const FIT = Object.freeze({
  fixed: "shrink-0",
  tree: "min-h-32 shrink-[100000] group-data-[mobile]/tool-stack:max-h-[40cqh]",
  details: "min-h-24 shrink",
});

/**
 * One panel of the tool stack under the strip: a kept effect's controls, or what the tool in
 * hand shows (a model tree and the Reference for a selection, a set of joints). Every panel is
 * the stack's one width, on the strip's translucent surface.
 *
 * A panel has a heading row only when it has something to do there: a title with the chevron
 * that folds it to that row (a view of the panel and nothing else — folded content stays
 * mounted and keeps working), and an X when it has something to remove. Without a `title` it
 * has none, and its first row is its own: a tree's `header` (the filter) or its content's.
 * `header` never scrolls; the body under it does, for a panel that gives way.
 *
 * `hidden` keeps a panel mounted while its tool is not up, so a tree keeps its expansion,
 * filter and scroll across a trip to another tool.
 *
 * @param {{ title?: import("react").ReactNode, label: string, summary?: import("react").ReactNode,
 *   header?: import("react").ReactNode, collapsible?: boolean, onClose?: (() => void) | null, closeLabel?: string,
 *   fit?: "fixed" | "tree" | "details", capped?: boolean, hidden?: boolean, defaultCollapsed?: boolean,
 *   children?: import("react").ReactNode }} props
 *   `label` names the panel for assistive technology ("Clip controls"), with a heading or
 *   without; the chevron and the X take their names from it, unless the X says what it does
 *   itself (`closeLabel`, "Clear selection"). `capped`: never taller than its heading and eight
 *   24px rows (`referenceRows.jsx`'s `InfoRow`: a reference's usual Type, Size, Volume, Center,
 *   Material and Color fit), scrolling inside itself beyond that.
 */
export default function ToolPanel({ title = null, label, summary = null, header = null, collapsible = false, onClose = null, closeLabel = "",
  fit = "fixed", capped = false, hidden = false, defaultCollapsed = false, children }) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const buttonClass = "flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
  return <section aria-label={label} hidden={hidden} data-tool-panel={fit}
    className={cn("pointer-events-auto flex w-full flex-col overflow-hidden rounded-md text-tiny", FLOATING_SURFACE_CLASS,
      collapsed ? "shrink-0" : FIT[fit], capped && "max-h-[calc(1.75rem+8*1.5rem+0.5rem+2px)]")}>
    {title ? <div className="flex min-h-7 shrink-0 items-center justify-end gap-0.5 pl-2 pr-1" data-tool-panel-heading="">
      <h3 className="mr-auto flex min-w-0 flex-1 items-center gap-2 text-xs font-normal">
        <span className="min-w-0 truncate">{title}</span>
        {summary ? <span className="shrink-0 text-tiny text-muted-foreground">{summary}</span> : null}
      </h3>
      {collapsible ? <button type="button" aria-label={`${collapsed ? "Expand" : "Collapse"} ${label.toLowerCase()}`} aria-expanded={!collapsed}
        className={buttonClass} onClick={() => setCollapsed(value => !value)}>
        {collapsed ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
      </button> : null}
      {onClose ? <button type="button" aria-label={closeLabel || `Close ${label.toLowerCase()}`}
        className={buttonClass} onClick={onClose}><X className="size-3" aria-hidden="true" /></button> : null}
    </div> : null}
    {header}
    <div hidden={collapsed} data-tool-panel-body=""
      className={cn("min-w-0", fit !== "fixed" && "min-h-0 flex-1 overflow-x-hidden overflow-y-auto")}>{children}</div>
  </section>;
}
