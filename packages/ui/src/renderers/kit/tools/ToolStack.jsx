import { createContext, useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ScrollArea } from "@hardcore/ui/primitives/scroll-area";
import { normalizeToolStack, toolPanelDefaultHeight } from "./toolStackLayout.js";

/**
 * What a panel of the stack reads of it (`ToolPanel.jsx`): the viewer's width, its size and folded
 * state as the person left them, how to write either back, and the room it has. `null` outside a
 * stack: a panel drawn alone opens at its defaults and keeps its state to itself.
 * @type {import("react").Context<null | {
 *   mobile: boolean,
 *   viewerWidth: number,
 *   size(key: string): { width?: number, height?: number } | null,
 *   widthOf(key: string): number | undefined,
 *   draft(id: string, size: { width?: number, height?: number } | null): void,
 *   defaultHeight(key: string): number,
 *   collapsed(id: string, fallback: boolean): boolean,
 *   settle(id: string, change: { width?: number, height?: number, collapsed?: boolean, fallback?: boolean }): void,
 *   room(): number,
 * }>}
 */
export const ToolStackContext = createContext(null);

/**
 * The tool stack under the strip: one column, the height the viewer leaves it, in which each
 * panel (`ToolPanel.jsx`) takes its content's height — up to its cap, for a panel that has one —
 * until the column runs out. The panels hang left-aligned under the strip, each at its own width:
 * `TOOL_PANEL_WIDTH` (`toolStackLayout.js`), unless the person has widened the panel
 * (`resizable`). The layout (`layout`: the sizes the person set, by panel; the folded panels) is
 * theirs, and is written back (`onLayoutChange`, a patch or a function of the layout as it
 * stands) once a gesture lets go, never per pointer move.
 *
 * @param {{ layout: { panels: object, collapsed: object },
 *   onLayoutChange(patch: object | ((layout: object) => object)): void, mobile?: boolean, hidden?: boolean,
 *   children?: import("react").ReactNode }} props
 */
export default function ToolStack({ layout: stored, onLayoutChange, mobile = false, hidden = false, children }) {
  const layout = useMemo(() => normalizeToolStack(stored), [stored]);
  const column = useRef(null);
  // A panel's size while a gesture on it is under way, so a panel that takes its width from
  // another (`widthFrom`) follows the drag rather than the release.
  const [drafts, setDrafts] = useState({});
  const draft = useCallback((id, size) => setDrafts(current => {
    if (size) return { ...current, [id]: size };
    if (!(id in current)) return current;
    const { [id]: _gone, ...rest } = current;
    return rest;
  }), []);
  // The column's own height — the viewer's less the strip above it and the insets: a tree opens
  // at half of it — and the viewer's width, which bounds a panel's.
  const [measured, setMeasured] = useState({ stack: 0, viewer: 0 });
  useLayoutEffect(() => {
    const element = column.current;
    if (!element) return undefined;
    const viewer = element.closest("[data-cad-scene-backdrop]");
    const measure = () => setMeasured(current => {
      const next = { stack: element.clientHeight, viewer: Math.round(viewer?.getBoundingClientRect().width || 0) };
      return current.stack === next.stack && current.viewer === next.viewer ? current : next;
    });
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (viewer) observer.observe(viewer);
    return () => observer.disconnect();
  }, []);
  // What one gesture on a panel leaves — a width, a cap, its folded state, or several at once (a
  // corner drag) — in one write. A panel folded as it starts is not written down: the record
  // holds only what differs.
  const settle = useCallback((id, change) => onLayoutChange(current => {
    const patch = {};
    if (change.width !== undefined || change.height !== undefined) {
      const size = { ...current.panels[id] };
      if (change.width !== undefined) size.width = change.width;
      if (change.height !== undefined) size.height = change.height;
      patch.panels = { ...current.panels, [id]: size };
    }
    if (change.collapsed !== undefined) {
      const next = { ...current.collapsed };
      if (change.collapsed === Boolean(change.fallback)) delete next[id]; else next[id] = change.collapsed;
      patch.collapsed = next;
    }
    return patch;
  }), [onLayoutChange]);
  const panels = useMemo(() => ({
    mobile,
    viewerWidth: measured.viewer,
    size: key => layout.panels[key] ?? null,
    widthOf: key => drafts[key]?.width ?? layout.panels[key]?.width,
    draft,
    defaultHeight: key => toolPanelDefaultHeight(key, measured.stack, mobile),
    collapsed: (id, fallback) => layout.collapsed[id] ?? fallback,
    settle,
    room: () => column.current?.clientHeight || 0,
  }), [mobile, measured, layout, drafts, draft, settle]);
  return <div ref={column} hidden={hidden} data-cad-tool-stack="" className="min-h-0 max-w-full flex-1">
    {/* The panels give way first (`ToolPanel.jsx`), in a column exactly the stack's height; if
        what cannot give way still does not fit, the column scrolls rather than being cut. The
        right and bottom insets leave a panel's handles room past its edges. */}
    {/* No visible bar of its own: it would stand outside the panels on every hover. A panel's
        own bar, inside it, is unaffected. */}
    <ScrollArea className="max-h-full" scrollbar={false} viewportProps={{ "data-tool-stack-scroller": "" }}>
      <div className="flex min-h-0 flex-col items-start gap-2 pb-1 pr-1" style={{ maxHeight: measured.stack || undefined }}>
        <ToolStackContext.Provider value={panels}>{children}</ToolStackContext.Provider>
      </div>
    </ScrollArea>
  </div>;
}
